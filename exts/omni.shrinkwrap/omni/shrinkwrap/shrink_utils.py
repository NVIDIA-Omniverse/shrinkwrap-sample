
# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.


import time
import asyncio
import carb
from pxr import Usd, UsdGeom, Vt, Gf, Sdf, UsdUtils
import omni.usd
from omni.convexdecomposition.bindings import _convexdecomposition

__all__ = [
    "get_child_meshes",
]


def get_child_meshes(prim: Usd.Prim):
    """Traverse source layer and fix all filepaths with backslashes."""

    meshes = []
    usd_context = omni.usd.get_context()
    stage = usd_context.get_stage()
    source_layer = stage.GetRootLayer()

    # this is a layer traversal callback that processes each spec path
    def _on_prim_spec_path(spec_path):
        if spec_path.IsPropertyPath():
            return

        prim_spec = source_layer.GetPrimAtPath(spec_path)
        if not prim_spec:
            return

        if prim_spec.typeName == "Mesh":
            meshes.append(spec_path)

    # traverse all prim spec paths under root path
    source_layer.Traverse(prim.GetPath(), _on_prim_spec_path)
    return meshes


def shrink_wrap(objects):
    usd_context = omni.usd.get_context()
    stage = usd_context.get_stage()

    all_meshes = [x for x in stage.TraverseAll() if x.IsA(UsdGeom.Mesh)]

    for prim in objects.get("prim_list", []):
        child_meshes = [x.GetPath().pathString for x in all_meshes if x.GetPath().HasPrefix(prim.GetPath())]
        if child_meshes:
            merge_path = prim.GetPath().AppendChild(prim.GetName() + "_premerge")
            args = {
                "meshPrimPaths": child_meshes,
                "considerMaterials": False,
                "materialAlbedoAsVertexColors": False,
                "originalGeomOption": 0,
                "rootPath": merge_path.pathString,
                "allowSingleMeshes": True,
                "considerAllAttributes": False,
                "mergePoint": 0
            }
            context = omni.scene.optimizer.core.ExecutionContext()
            context.usdStageId = UsdUtils.StageCache().Get().Insert(stage).ToLongInt()
            context.generateReport = 1
            context.captureStats = 1
            success, result = omni.kit.commands.execute("SceneOptimizerOperation", operation="merge", args=args)
            pre_merged = result[-1]

            if not success:
                return

            merge_meshes = []
            for merged in pre_merged:
                merged = stage.GetPrimAtPath(merged)
                if not merged:
                    continue

                vis_attr = merged.GetAttribute("visibility")
                if vis_attr and vis_attr.Get() == "invisible":
                    stage.RemovePrim(merged.GetPath())
                    continue

                for attr in merged.GetAttributes():
                    if attr.GetName().startswith("primvars:"):
                        merged.RemoveProperty(attr.GetName())

                for child in merged.GetAllChildren():
                    stage.RemovePrim(child.GetPath())

                merge_meshes.append(merged.GetPath().pathString)

            args["rootPath"] = prim.GetPath().AppendChild(prim.GetName() + "_merged").pathString
            args["meshPrimPaths"] = merge_meshes
            args["originalGeomOption"] = 1

            success, result = omni.kit.commands.execute("SceneOptimizerOperation", operation="merge", args=args)
            post_merged = result[-1]

            if not success:
                carb.log_error("Failed to run Merge Static Mesh Operation - exiting.")
                return
            
            if len(post_merged) == 0:
                carb.log_error("No mesh returned from Merge Static Mesh Operation - exiting.")

            if len(post_merged) > 1:
                carb.log_warn("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
                carb.log_warn("More than one mesh was returned from the Merge Static Mesh Operation (see README).\nThe first mesh will be choosen for shrinkwrap generation")
                carb.log_warn("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

            # To generate wrap meshes for all post merged meshes you could loop through them, but this can take a long time.
            # merged_meshes = [stage.GetPrimAtPath(prim_path) for prim_path in post_merged if stage.GetPrimAtPath(prim_path)]
            # wrapper = meshWrap()
            # for merged_mesh in merge_meshes:
            #     wrapper.do_convex(merged_mesh)

            merged = stage.GetPrimAtPath(post_merged[0])
            if not merged:
                continue

            wrapper = meshWrap()
            wrapper.do_convex(merged)


class meshWrap():
    def __init__(self):
        self._convexdecomposition = None

    def _notify_complete(self, handle):
        carb.log_info("Got notify complete callback!" + str(handle))

    def do_convex(self, meshPrim):
        asyncio.ensure_future(self._convex_async(meshPrim))

    async def _convex_async(self, prim):
        self._convexdecomposition = _convexdecomposition.acquire_convexdecomposition_interface()
        handle = self._convexdecomposition.create_vhacd()
        meshPrim = _convexdecomposition.SimpleMesh()
        mesh = UsdGeom.Mesh(prim)

        vertices = []
        for v in mesh.GetPointsAttr().Get():
            vertices += list(v)

        meshPrim.vertices = vertices
        meshPrim.indices = mesh.GetFaceVertexIndicesAttr().Get()

        p = _convexdecomposition.Parameters()
        p.error_percentage = .01
        p.max_hull_vertices = 64
        p.max_convex_hull_count = 1
        p.voxel_resolution = 10000
        p.voxel_fill_mode = _convexdecomposition.VoxelFillMode.FLOOD_FILL
        p.notify_complete_callback = self._notify_complete

        self._convexdecomposition.begin_vhacd(handle, meshPrim, p)

        carb.log_info(f"Starting {prim.GetName()} convex decomposition.")
        while not self._convexdecomposition.is_complete(handle):
            time.sleep(0.01)
        carb.log_info(f"{prim.GetName()} convex decomposition complete.")

        chull = _convexdecomposition.SimpleMesh()
        ok = self._convexdecomposition.get_convex_hull(handle, 0, chull)
        if ok:
            carb.log_info(f"Got hull for {prim.GetName()}")
            mesh.GetFaceVertexIndicesAttr().Set(chull.indices)

            vertices = [Gf.Vec3f(chull.vertices[i:i + 3]) for i in range(0, len(chull.vertices), 3)]
            mesh.GetPointsAttr().Set(vertices)
            
            faces = []
            for _ in range(int(len(chull.indices) / 3)):
                faces.append(3)
            mesh.GetFaceVertexCountsAttr().Set(faces)

        else:
            carb.log_error(f"Failed hull for {prim.GetName()}")

        self._convexdecomposition.release_vhacd(handle)
        self._convexdecomposition = None

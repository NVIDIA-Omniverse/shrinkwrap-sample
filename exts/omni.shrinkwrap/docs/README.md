# Overview

This extension merges all meshes under a transform and creates a convex hull.

### Usage

- Right click on transform with meshes in stage editor and select > Wrap Tool > Convex Wrap

### Limitations

- This extension uses Scene Optimizer to try to combine meshes into a single prim because the wrap mesh can only be generated on a single prim. The main reason why you could get more than one prim back after doing a "merge static mesh" operation (Window -> Utilities -> Scene Optimizer -> + Add Scene Optimizer Process -> Merge Static Meshes).

  - Scene Optimizer does some limiting on the amount of mesh components that are available per merged prim - how many verts you can have in a merged setup for the bucketing algorithm.

  - If that is happening in this extension, directly use the Scene Optimizer framework and utilize mesh decimation (Window -> Utilities -> Scene Optimizer -> + Add Scene Optimizer Process -> Decimate Meshes) in combination with Merge Static Meshes to achieve the desired setup for the shrinkwrap step.

- The physx convex decomposition extension is hard limited to 64 vertices. 

  - You can enable subdivision to add more definition to the shrink wrap mesh.

- Mesh is created with no UVs

  - Use Window -> Utilities -> Scene Optimizer -> + Add Scene Optimizer Process -> Auto UV Unwrap or Generate Projection UVs (triplanar works great) to add UVs to your wrap mesh.

### Screenshot

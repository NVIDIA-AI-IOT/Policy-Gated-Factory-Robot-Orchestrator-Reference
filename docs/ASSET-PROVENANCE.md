# Asset provenance

This page records the sources of the documentation media, two USD scene
compositions, and the NVIDIA Isaac assets they reference. The repository's
Apache-2.0 source license does not grant rights to separately retrieved assets
or to third-party content shown in screenshots and recordings. This inventory
does not assign a separate license to those assets.

## Included media and scene compositions

| Path | Source |
|---|---|
| `docs/images/reference-architecture.png` | Architecture diagram supplied by the project owner on 2026-09-15; copied without modification. |
| `docs/images/orchestration-console.png` | Dashboard screenshot supplied by the project owner; added on 2026-09-13 without modification. |
| `docs/images/isaac-sim/cell-overview.jpg` | Captured from the Isaac Sim 6.0.0-dev2 reference scene on 2026-09-13; no retouching. |
| `docs/images/isaac-sim/sorting-stations.jpg` | Captured from the Isaac Sim 6.0.0-dev2 reference scene on 2026-09-13; no retouching. |
| `docs/images/isaac-sim/left-arm-closeup.jpg` | Captured from the Isaac Sim 6.0.0-dev2 reference scene on 2026-09-14; no retouching. |
| `docs/images/isaac-sim/objects-and-totes.jpg` | Captured from the Isaac Sim 6.0.0-dev2 reference scene on 2026-09-13; no retouching. |
| `docs/images/pgfr-project-video-preview.gif` | Converted on 2026-09-14 from an owner-supplied recording showing the Console and NVIDIA Isaac scene. |
| `reference/isaac-cell/deployment/our_factory.usda` | ASCII scene composition introduced on 2026-06-21; references the remote assets below. |
| `reference/isaac-cell/our_factory.usda` | ASCII scene composition introduced on 2026-06-21; references the remote assets below. |

The scene captures used a temporary viewing camera. See the
[scene guide](ISAAC-SIM-SCENE.md) for the component descriptions.

## Project preview

The animated GIF was converted from the owner-supplied `PGFR-demo-3xspeed.mp4`
recording of the Console and NVIDIA Isaac scene. That source recording is
absent from the current source tree. The GIF has no audio or embedded codec
implementation.

Conversion used ImageIO-FFmpeg 0.6.0's Linux x86-64 FFmpeg 7.0.2-static
executable, identified as John Van Sickle's GPL-3.0-or-later build.
[Third-party notices](../THIRD-PARTY-NOTICES.md#codec-prerequisites) describe
the separate training and runtime codec dependencies.

## Remotely referenced NVIDIA Isaac assets

The two USDA files are text compositions. They do not embed the asset binaries
below; Isaac Sim retrieves them from NVIDIA-hosted HTTPS locations. Those
assets and the NVIDIA content shown in the scene captures retain their
applicable NVIDIA Isaac terms; see
[Isaac Sim licensing](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/common/licenses-isaac-sim.html).
A retrieval URL identifies a source, not an additional redistribution grant.

| Remote asset URL | Referencing tracked USDA files |
|---|---|
| [Warehouse 20x20 environment](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Environments/warehouse_20x20_envi/warehouse_20x20_envi.usd) | <code>reference/isaac-cell/deployment/our_factory.usda</code>; <code>reference/isaac-cell/our_factory.usda</code> |
| [Blue block](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Props/Blocks/blue_block.usd) | <code>reference/isaac-cell/deployment/our_factory.usda</code>; <code>reference/isaac-cell/our_factory.usda</code> |
| [Green block](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Props/Blocks/green_block.usd) | <code>reference/isaac-cell/deployment/our_factory.usda</code>; <code>reference/isaac-cell/our_factory.usda</code> |
| [Red block](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Props/Blocks/red_block.usd) | <code>reference/isaac-cell/deployment/our_factory.usda</code>; <code>reference/isaac-cell/our_factory.usda</code> |
| [RidgebackFranka](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Robots/Clearpath/RidgebackFranka/ridgeback_franka.usd) | <code>reference/isaac-cell/deployment/our_factory.usda</code>; <code>reference/isaac-cell/our_factory.usda</code> |
| [Franka Panda](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Robots/FrankaRobotics/FrankaPanda/franka.usd) | <code>reference/isaac-cell/deployment/our_factory.usda</code>; <code>reference/isaac-cell/our_factory.usda</code> |
| [Azure Kinect](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Samples/Leonardo/Props/azure_kinect.usd) | <code>reference/isaac-cell/deployment/our_factory.usda</code>; <code>reference/isaac-cell/our_factory.usda</code> |

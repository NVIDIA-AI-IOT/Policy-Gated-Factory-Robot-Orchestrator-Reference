# Asset provenance

This inventory covers the eight tracked media and USD composition
files in the Policy-Gated Factory Robot Orchestrator Reference release tree, plus the ten distinct NVIDIA Isaac
6.0 assets referenced remotely by the USD compositions.

It records technical and Git-history evidence for release review. A commit
author address, file presence in NVIDIA infrastructure, or an NVIDIA-hosted
runtime URL is not by itself a copyright assignment or distribution grant.
Unless an item has a separately established grant, its rights status below is
<strong>pending owner/OSRB confirmation</strong>.

## Tracked assets

| Tracked path | File/media metadata | Bytes | SHA-256 | Introduction history | Rights status |
|---|---|---:|---|---|---|
| <code>docs/PGFR_Demo.mp4</code> | MP4; H.264 High; 2258x720; yuv420p; 30 fps; 46.766667 s; one video stream and no audio stream | 2,507,505 | <code>ed8f9e0eebb4693b21ba17a4687e315f031aa8593e181a2b2e25fe6f79de989c</code> | <code>4cc390c2e53f5d6a45f13ce5c1769b9c322608ca</code>; 2026-07-07; <code>mmallick@nvidia.com</code> | pending owner/OSRB confirmation; H.264/codec review also pending |
| <code>docs/pgfr-spine-reference-architecture.png</code> | PNG; 1600x900; RGBA | 157,371 | <code>6c855c0c722f08ffbccc8a8e56fd643f200b6370a025485ed53b6a4ee508acd3</code> | <code>b32e7f278129558bbd75f415c4962cde135dc57a</code>; 2026-07-07; <code>mmallick@nvidia.com</code> | pending owner/OSRB confirmation |
| <code>docs/pgfr-spine-deployment.svg</code> | SVG; viewBox 0 0 1440 820 | 5,973 | <code>a8e29275222e583e265ee3ba9543d1f97fd2a48940cdd7576c6c25d5229825a7</code> | <code>b32e7f278129558bbd75f415c4962cde135dc57a</code>; 2026-07-07; <code>mmallick@nvidia.com</code> | pending owner/OSRB confirmation |
| <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/deployment/our_factory.usda</code> | ASCII USDA scene composition; remotely references Isaac assets | 98,335 | <code>1a5605cacb0568e08989472c5b2a80be2f8de021837512fbfd577ebca5a39381</code> | <code>a98a5e3679b8ba923fd787832b15cd87a4b280c8</code>; 2026-06-21; <code>mmallick@nvidia.com</code> | pending owner/OSRB confirmation |
| <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/factory_scene.usda</code> | ASCII USDA scene composition; remotely references Isaac assets | 8,961 | <code>da753cd4e7dcf1ce9acaa32dabb66e85454c3af36597b27bbf382c18fbb9e899</code> | <code>a98a5e3679b8ba923fd787832b15cd87a4b280c8</code>; 2026-06-21; <code>mmallick@nvidia.com</code> | pending owner/OSRB confirmation |
| <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/my_pick_place.usda</code> | ASCII USDA scene composition; remotely references Isaac assets | 8,963 | <code>6074c3fd8bc886f80159004cb48c0f38e51d0ba55d689a9ca4707a29d688e0b3</code> | <code>a98a5e3679b8ba923fd787832b15cd87a4b280c8</code>; 2026-06-21; <code>mmallick@nvidia.com</code> | pending owner/OSRB confirmation |
| <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/our_factory.usda</code> | ASCII USDA scene composition; remotely references Isaac assets | 79,943 | <code>beb82c9da4ce1d101f751649c23c637f932a559530b010de3ba7baaeb404fb7f</code> | <code>a98a5e3679b8ba923fd787832b15cd87a4b280c8</code>; 2026-06-21; <code>mmallick@nvidia.com</code> | pending owner/OSRB confirmation |
| <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/our_factory_backup_1505.usda</code> | ASCII USDA scene composition; remotely references Isaac assets | 56,612 | <code>957d7ab2ccd056c0d6d14c594a40af91add69ad3e175861689d83339d02c9f96</code> | <code>a98a5e3679b8ba923fd787832b15cd87a4b280c8</code>; 2026-06-21; <code>mmallick@nvidia.com</code> | pending owner/OSRB confirmation |

The Git introduction records above are evidence of when the tracked bytes
entered this repository, not proof of ownership or authorization.

## Remotely referenced NVIDIA Isaac assets

The five USDA files are text compositions. They do not embed the following
asset binaries; Isaac Sim retrieves them at runtime from NVIDIA-hosted HTTPS
locations. Rights status for every row is <strong>pending owner/OSRB
confirmation</strong>.

| Remote asset URL | Referencing tracked USDA files |
|---|---|
| [Grid default environment](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Environments/Grid/default_environment.usd) | <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/factory_scene.usda</code> |
| [Simple Warehouse](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Environments/Simple_Warehouse/warehouse.usd) | <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/my_pick_place.usda</code> |
| [Warehouse 20x20 environment](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Environments/warehouse_20x20_envi/warehouse_20x20_envi.usd) | <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/deployment/our_factory.usda</code>; <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/our_factory.usda</code>; <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/our_factory_backup_1505.usda</code> |
| [Blue block](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Props/Blocks/blue_block.usd) | all five tracked USDA compositions |
| [Green block](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Props/Blocks/green_block.usd) | all five tracked USDA compositions |
| [Red block](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Props/Blocks/red_block.usd) | all five tracked USDA compositions |
| [Small KLT bin](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Props/KLT_Bin/small_KLT.usd) | <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/factory_scene.usda</code>; <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/my_pick_place.usda</code>; <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/our_factory_backup_1505.usda</code> |
| [RidgebackFranka](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Robots/Clearpath/RidgebackFranka/ridgeback_franka.usd) | <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/deployment/our_factory.usda</code>; <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/our_factory.usda</code>; <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/our_factory_backup_1505.usda</code> |
| [Franka Panda](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Robots/FrankaRobotics/FrankaPanda/franka.usd) | all five tracked USDA compositions |
| [Azure Kinect](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Samples/Leonardo/Props/azure_kinect.usd) | all five tracked USDA compositions |

## Release gate

Before public release, the owner/OSRB record should confirm the distribution
right for each tracked asset, the permission to publish compositions that
reference NVIDIA-hosted Isaac assets, and the H.264/codec treatment of the demo
video. This document deliberately does not infer those approvals.

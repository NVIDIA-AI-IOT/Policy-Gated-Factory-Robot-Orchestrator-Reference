# Asset provenance

This inventory covers the dashboard screenshot, four Isaac Sim scene captures,
the supplied demo video and its GIF preview, and five USD composition files in
the Policy-Gated Factory Robot Orchestrator Reference release tree, plus the ten
distinct NVIDIA Isaac 6.0 assets referenced remotely by the USD compositions.

It records technical and Git-history evidence for release review. A commit
author address, file presence in NVIDIA infrastructure, or an NVIDIA-hosted
runtime URL is not by itself a copyright assignment or distribution grant.
Unless an item has a separately established grant, its rights status below is
<strong>pending owner/OSRB confirmation</strong>.

## Tracked assets

| Tracked path | File/media metadata | Bytes | SHA-256 | Introduction history | Rights status |
|---|---|---:|---|---|---|
| <code>docs/images/orchestration-console.png</code> | PNG; 3796x1986; RGBA | 259,824 | <code>113b0f92992a26bc33024558c8d007d8a6b0c6043de66cdbcfcf26a093cae483</code> | Added to release sources; 2026-09-13. Owner-supplied dashboard screenshot; copied without modification. | pending owner/OSRB confirmation |
| <code>docs/images/isaac-sim/cell-overview.jpg</code> | JPEG; 1920x1080; RGB; quality 90, 4:4:4 | 510,982 | <code>d092cca4010222f35e5c414729be6efe4abecee0a0b8e3348c7acd743276b5bb</code> | Captured 2026-09-13 from the running Isaac Sim 6.0.0-dev2 reference scene using a temporary viewing camera; no retouching. | pending owner/OSRB confirmation; rendered NVIDIA Isaac scene assets |
| <code>docs/images/isaac-sim/sorting-stations.jpg</code> | JPEG; 1920x1080; RGB; quality 90, 4:4:4 | 374,020 | <code>09e2ed28906d02518a4eaa3618a5bd5e8a7d286821de2304414130c05e080b6f</code> | Captured 2026-09-13 from the running Isaac Sim 6.0.0-dev2 reference scene using a temporary viewing camera; no retouching. | pending owner/OSRB confirmation; rendered NVIDIA Isaac scene assets |
| <code>docs/images/isaac-sim/left-arm-closeup.jpg</code> | JPEG; 1600x1280; RGB; quality 90, 4:4:4 | 241,347 | <code>54f12b29c6d4de5d4715e49bb77317eb17c57eb484ac68651fd5a448d9b3b018</code> | Captured 2026-09-14 from the running Isaac Sim 6.0.0-dev2 reference scene using a temporary viewing camera; no retouching. | pending owner/OSRB confirmation; rendered NVIDIA Isaac scene assets |
| <code>docs/images/isaac-sim/objects-and-totes.jpg</code> | JPEG; 1920x1080; RGB; quality 90, 4:4:4 | 349,031 | <code>f75874924a13474c39e77bc7af34b5ab37f02f6482c5b52ac6b8b6eefd837946</code> | Captured 2026-09-13 from the running Isaac Sim 6.0.0-dev2 reference scene using a temporary viewing camera; no retouching. | pending owner/OSRB confirmation; rendered NVIDIA Isaac scene assets |
| <code>docs/videos/pgfr-demo-3x.mp4</code> | MP4; H.264 video, AAC audio; 1280x720; 30 fps; 62.2 s | 20,700,409 | <code>5ee24a28a81fd993120ecca59a0c478cb821bd0c525baab486d1c4ae23efb7f4</code> | Supplied by the project owner on 2026-09-14 as PGFR-demo-3xspeed.mp4; 3× speed per the supplied recording; copied without modification. Recording date not established. | pending owner/OSRB confirmation; recorded Console and NVIDIA Isaac scene assets |
| <code>docs/images/pgfr-demo-preview.gif</code> | GIF; 800x450; 10 fps; 622 frames; 62.2 s; looping; no audio | 9,598,395 | <code>ede7b608ca8d3984453cd426f5e04276cb694a28a0b4e87995cf65fcea6243fd</code> | Derived 2026-09-14 from the supplied demo MP4 with FFmpeg 7.0.2. Full duration and playback speed preserved; downscaled, sampled at 10 fps, and palette-encoded with 128 colors and Bayer dithering. No generated content. | pending owner/OSRB confirmation; recorded Console and NVIDIA Isaac scene assets |
| <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/deployment/our_factory.usda</code> | ASCII USDA scene composition; remotely references Isaac assets | 98,335 | <code>1a5605cacb0568e08989472c5b2a80be2f8de021837512fbfd577ebca5a39381</code> | <code>a98a5e3679b8ba923fd787832b15cd87a4b280c8</code>; 2026-06-21; <code>mmallick@nvidia.com</code> | pending owner/OSRB confirmation |
| <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/factory_scene.usda</code> | ASCII USDA scene composition; remotely references Isaac assets | 8,961 | <code>da753cd4e7dcf1ce9acaa32dabb66e85454c3af36597b27bbf382c18fbb9e899</code> | <code>a98a5e3679b8ba923fd787832b15cd87a4b280c8</code>; 2026-06-21; <code>mmallick@nvidia.com</code> | pending owner/OSRB confirmation |
| <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/my_pick_place.usda</code> | ASCII USDA scene composition; remotely references Isaac assets | 8,963 | <code>6074c3fd8bc886f80159004cb48c0f38e51d0ba55d689a9ca4707a29d688e0b3</code> | <code>a98a5e3679b8ba923fd787832b15cd87a4b280c8</code>; 2026-06-21; <code>mmallick@nvidia.com</code> | pending owner/OSRB confirmation |
| <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/our_factory.usda</code> | ASCII USDA scene composition; remotely references Isaac assets | 79,943 | <code>beb82c9da4ce1d101f751649c23c637f932a559530b010de3ba7baaeb404fb7f</code> | <code>a98a5e3679b8ba923fd787832b15cd87a4b280c8</code>; 2026-06-21; <code>mmallick@nvidia.com</code> | pending owner/OSRB confirmation |
| <code>reference/policy-gated-factory-robot-orchestrator-reference/isaac-cell/our_factory_backup_1505.usda</code> | ASCII USDA scene composition; remotely references Isaac assets | 56,612 | <code>957d7ab2ccd056c0d6d14c594a40af91add69ad3e175861689d83339d02c9f96</code> | <code>a98a5e3679b8ba923fd787832b15cd87a4b280c8</code>; 2026-06-21; <code>mmallick@nvidia.com</code> | pending owner/OSRB confirmation |

The Git introduction records above are evidence of when the tracked bytes
entered this repository, not proof of ownership or authorization.

The scene captures used a temporary viewing camera; existing model cameras and
simulation play state were preserved, and the temporary camera was removed.
See the [scene guide](ISAAC-SIM-SCENE.md) for the component descriptions.

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
right for each tracked asset and the permission to publish compositions that
reference NVIDIA-hosted Isaac assets. This document deliberately does not infer
those approvals.

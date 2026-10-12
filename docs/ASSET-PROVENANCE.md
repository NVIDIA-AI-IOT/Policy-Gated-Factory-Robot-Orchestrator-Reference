# Asset provenance

This inventory covers the architecture diagram, dashboard screenshot, four Isaac Sim
scene captures, the supplied project video and its preview, and two USD composition files in
the Policy-Gated Factory Robot Orchestrator Reference release tree, plus the seven
distinct NVIDIA Isaac 6.0 assets referenced remotely by the USD compositions.

It records technical and Git-history evidence for release review. A commit
author address, file presence in NVIDIA infrastructure, or an NVIDIA-hosted
runtime URL is not by itself a copyright assignment or distribution grant.
Unless an item has a separately established grant, its rights status below is
<strong>pending owner/OSRB confirmation</strong>.

## Tracked assets

| Tracked path | File/media metadata | Bytes | SHA-256 | Introduction history | Rights status |
|---|---|---:|---|---|---|
| <code>docs/images/reference-architecture.png</code> | PNG; 1608x1083; indexed color | 59,639 | <code>3a3d99a0acecf3dd9ba108d851978df8792a3eb2d2653577060ac27946f45768</code> | Architecture diagram supplied by the project owner on 2026-09-15; copied without modification. | pending owner/OSRB confirmation |
| <code>docs/images/orchestration-console.png</code> | PNG; 3796x1986; RGBA | 259,824 | <code>113b0f92992a26bc33024558c8d007d8a6b0c6043de66cdbcfcf26a093cae483</code> | Added to release sources; 2026-09-13. Owner-supplied dashboard screenshot; copied without modification. | pending owner/OSRB confirmation |
| <code>docs/images/isaac-sim/cell-overview.jpg</code> | JPEG; 1920x1080; RGB; quality 90, 4:4:4 | 510,982 | <code>d092cca4010222f35e5c414729be6efe4abecee0a0b8e3348c7acd743276b5bb</code> | Captured 2026-09-13 from the running Isaac Sim 6.0.0-dev2 reference scene using a temporary viewing camera; no retouching. | pending owner/OSRB confirmation; rendered NVIDIA Isaac scene assets |
| <code>docs/images/isaac-sim/sorting-stations.jpg</code> | JPEG; 1920x1080; RGB; quality 90, 4:4:4 | 374,020 | <code>09e2ed28906d02518a4eaa3618a5bd5e8a7d286821de2304414130c05e080b6f</code> | Captured 2026-09-13 from the running Isaac Sim 6.0.0-dev2 reference scene using a temporary viewing camera; no retouching. | pending owner/OSRB confirmation; rendered NVIDIA Isaac scene assets |
| <code>docs/images/isaac-sim/left-arm-closeup.jpg</code> | JPEG; 1600x1280; RGB; quality 90, 4:4:4 | 241,347 | <code>54f12b29c6d4de5d4715e49bb77317eb17c57eb484ac68651fd5a448d9b3b018</code> | Captured 2026-09-14 from the running Isaac Sim 6.0.0-dev2 reference scene using a temporary viewing camera; no retouching. | pending owner/OSRB confirmation; rendered NVIDIA Isaac scene assets |
| <code>docs/images/isaac-sim/objects-and-totes.jpg</code> | JPEG; 1920x1080; RGB; quality 90, 4:4:4 | 349,031 | <code>f75874924a13474c39e77bc7af34b5ab37f02f6482c5b52ac6b8b6eefd837946</code> | Captured 2026-09-13 from the running Isaac Sim 6.0.0-dev2 reference scene using a temporary viewing camera; no retouching. | pending owner/OSRB confirmation; rendered NVIDIA Isaac scene assets |
| <code>docs/videos/pgfr-project-video.mp4</code> | MP4; H.264 video, AAC audio; 1280x720; 30 fps; 62.2 s | 20,700,409 | <code>5ee24a28a81fd993120ecca59a0c478cb821bd0c525baab486d1c4ae23efb7f4</code> | Supplied by the project owner on 2026-09-14 as PGFR-demo-3xspeed.mp4; 3× speed per the supplied recording; copied without modification. Recording date not established. | pending owner/OSRB confirmation; recorded Console and NVIDIA Isaac scene assets |
| <code>docs/images/pgfr-project-video-preview.gif</code> | GIF; 800x450; 10 fps; 622 frames; 62.2 s; looping; no audio | 9,598,395 | <code>ede7b608ca8d3984453cd426f5e04276cb694a28a0b4e87995cf65fcea6243fd</code> | Derived 2026-09-14 from the supplied project video with FFmpeg 7.0.2. Full duration and playback speed preserved; downscaled, sampled at 10 fps, and palette-encoded with 128 colors and Bayer dithering. No generated content. | pending owner/OSRB confirmation; recorded Console and NVIDIA Isaac scene assets |
| <code>reference/isaac-cell/deployment/our_factory.usda</code> | ASCII USDA scene composition; remotely references Isaac assets | 98,335 | <code>1a5605cacb0568e08989472c5b2a80be2f8de021837512fbfd577ebca5a39381</code> | <code>a98a5e3679b8ba923fd787832b15cd87a4b280c8</code>; 2026-06-21; <code>mmallick@nvidia.com</code> | pending owner/OSRB confirmation |
| <code>reference/isaac-cell/our_factory.usda</code> | ASCII USDA scene composition; remotely references Isaac assets | 79,943 | <code>beb82c9da4ce1d101f751649c23c637f932a559530b010de3ba7baaeb404fb7f</code> | <code>a98a5e3679b8ba923fd787832b15cd87a4b280c8</code>; 2026-06-21; <code>mmallick@nvidia.com</code> | pending owner/OSRB confirmation |

The Git introduction records above are evidence of when the tracked bytes
entered this repository, not proof of ownership or authorization.

The scene captures used a temporary viewing camera; existing model cameras and
simulation play state were preserved, and the temporary camera was removed.
See the [scene guide](ISAAC-SIM-SCENE.md) for the component descriptions.

## Project video and preview

`docs/videos/pgfr-project-video.mp4` is a prerecorded media **data file** for
the README. It contains H.264 Main-profile video (1280×720, 30 fps, yuv420p)
and AAC-LC audio (48 kHz, stereo), with a duration of 62.20 seconds. It contains
no FFmpeg executable, encoder implementation, or shared library. The robot
services and dataset pipeline do not use this documentation video as an input.
A viewer's browser or media player decodes it.

The file was supplied by the project owner and copied unchanged. Its container
metadata identifies `https://clipchamp.com` as the encoder application. That
tag does not establish the original recorder, export settings, encoder build,
or rights to the recording and audio. Rights to publish the recording and audio
need owner confirmation. The unrecorded export/build details are evidence gaps;
they are not, by themselves, findings of a licensing violation. Any request for
additional technical evidence should be tied to the release scope and the OSRB
reviewer's questions.

The GIF preview is a separate media data file with no audio. The retained
preparation record identifies ImageIO-FFmpeg `0.6.0`'s Linux x86-64
`7.0.2-static` executable for the preview conversion. Its bytes match the
executable bundled in the published PyPI wheel; the historical download
source was not recorded.
That executable identifies John Van Sickle's static build, reports GPL-3.0-or-later,
and has `--enable-gpl` and `--enable-version3`, without `--enable-nonfree`.
It is a different build from the NVIDIA FFmpeg 8 executable installed on Thor.
The original conversion command was not retained; the recorded conversion
settings and resulting GIF metadata are listed above.

The [codec inventory](codec-inventory.json) records the media hashes and the
identified tool's hash, configuration, license report, and compiled codecs.
[Third-party notices](../THIRD-PARTY-NOTICES.md#codec-use-and-build-evidence)
separately describe training and runtime codec software. Treating the MP4 and
GIF as data files does not settle content rights or codec/patent review.

## Remotely referenced NVIDIA Isaac assets

The two USDA files are text compositions. They do not embed the following
asset binaries; Isaac Sim retrieves them at runtime from NVIDIA-hosted HTTPS
locations. Rights status for every row is <strong>pending owner/OSRB
confirmation</strong>.

| Remote asset URL | Referencing tracked USDA files |
|---|---|
| [Warehouse 20x20 environment](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Environments/warehouse_20x20_envi/warehouse_20x20_envi.usd) | <code>reference/isaac-cell/deployment/our_factory.usda</code>; <code>reference/isaac-cell/our_factory.usda</code> |
| [Blue block](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Props/Blocks/blue_block.usd) | <code>reference/isaac-cell/deployment/our_factory.usda</code>; <code>reference/isaac-cell/our_factory.usda</code> |
| [Green block](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Props/Blocks/green_block.usd) | <code>reference/isaac-cell/deployment/our_factory.usda</code>; <code>reference/isaac-cell/our_factory.usda</code> |
| [Red block](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Props/Blocks/red_block.usd) | <code>reference/isaac-cell/deployment/our_factory.usda</code>; <code>reference/isaac-cell/our_factory.usda</code> |
| [RidgebackFranka](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Robots/Clearpath/RidgebackFranka/ridgeback_franka.usd) | <code>reference/isaac-cell/deployment/our_factory.usda</code>; <code>reference/isaac-cell/our_factory.usda</code> |
| [Franka Panda](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Robots/FrankaRobotics/FrankaPanda/franka.usd) | <code>reference/isaac-cell/deployment/our_factory.usda</code>; <code>reference/isaac-cell/our_factory.usda</code> |
| [Azure Kinect](https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.0/Isaac/Samples/Leonardo/Props/azure_kinect.usd) | <code>reference/isaac-cell/deployment/our_factory.usda</code>; <code>reference/isaac-cell/our_factory.usda</code> |

## Release gate

Before public release, the owner/OSRB record should confirm the distribution
right for each tracked asset and the permission to publish compositions that
reference NVIDIA-hosted Isaac assets. This document deliberately does not infer
those approvals.

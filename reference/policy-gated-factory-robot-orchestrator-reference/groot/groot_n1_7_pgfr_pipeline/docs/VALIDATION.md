# Qualify a user-trained policy

Every user-generated dataset and checkpoint needs its own qualification.
Existing developer demonstrations and offline source tests do not establish
that a new checkpoint succeeds. No training or simulator run is performed by
the conversion/export checks.

1. **Data acceptance:** preserve capture manifests and rejected-attempt records;
   audit camera timing, applied action provenance, episode counts, finite values,
   FK source hashes, absolute and relative statistics, and train/validation/test
   separation by complete sequence. Decode sample and boundary video frames.
2. **Training evidence:** record base/backbone revisions and terms, upstream Git
   revision and patch hash, dataset hashes, full launch arguments, actual final
   step, loss/held-out metrics, hardware, peak GPU memory, and elapsed time.
   The public recipe currently provides no measured RTX training budget.
3. **Artifact integrity:** export your own checkpoint, verify every checksum,
   and retain dataset/training provenance and NVIDIA attribution. Confirm both
   policy servers load the same identity. Passing hashes is not action success.
4. **Single-arm simulation:** in an isolated test scene, exercise every required
   color/shape, arm, pose/layout, and accumulated tote context. Measure physical
   grasp, object tracking, release, settling, distractor motion and final tote
   compartment placement. Include failures; no automatic physical redispatch.
5. **Complete orchestration:** run the serial six-object task in the admitted
   order, fresh visual verification after every action, then both scripted AMR
   tote transfers. The optional paired path requires its separate explicit
   configuration and mixed-color order. Refer to the [runtime guide](../../README.md)
   for the current admitted serial/paired sequences.
6. **Release evidence:** report sample counts, acceptance/failure criteria,
   success rates, held-out coverage and limitations for this checkpoint. Do not
   reuse historical success claims, an exact 768-episode count, or a developer
   checkpoint label as evidence for new artifacts.

The model-free `expert_capture` profile is for collecting expert demonstrations.
Its grasp/camera acceptance must be run on real Isaac before gathering a large
corpus. It is not the deployed GR00T profile. Successful expert rollouts do not
prove that a policy learned from them will behave equivalently.

The source license does not grant rights to redistribute third-party model
weights, downloaded assets, or externally collected data. Follow the
[project release scope](../../../../../docs/RELEASE-SCOPE.md) and applicable
artifact terms for anything you intend to publish.

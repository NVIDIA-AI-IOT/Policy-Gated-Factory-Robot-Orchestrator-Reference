# GR00T relay

The relay connects the Isaac action executor to a GR00T policy server using a
bounded, versioned request protocol. The current shared-checkpoint deployment
uses one policy process and one
[`native_droid_relay_batch2.py`](native_droid_relay_batch2.py) process per
arm.

The batch-two relay provides the native-DROID single-frame observation and
action contract used by the integrated runtime. When `PGFR_SERVICE_STATE_PATH`
is configured, it atomically publishes the active model, checkpoint,
fingerprint, policy endpoint, relay endpoint, and protocol identity. The Isaac
executor validates that service-state record before dispatching actions.

Policy and relay listeners must remain on loopback. The executor-facing wire
format uses length-prefixed Python pickle and must not be exposed to an
untrusted network.

[`native_droid_relay_single_frame.py`](native_droid_relay_single_frame.py) is
retained for the earlier specialist serving profiles. It is not used by the
current shared Order744-cont24 demo path.

Install and configure the current relay through the repository's GR00T setup
and service files rather than launching an untracked process manually.

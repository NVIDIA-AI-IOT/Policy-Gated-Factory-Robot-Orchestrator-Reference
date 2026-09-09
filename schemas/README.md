# Schemas

`floor-service.openapi.json` is the generated public PGFR Spine HTTP contract;
its unit test fails whenever the implementation and committed specification
drift. `cell-protocol/` defines the JSON payloads carried by the ROS topics
between PGFR Spine and the Isaac cell. The action-registry tests keep the command
action set aligned with the packaged cell and its two-arm deployment route.

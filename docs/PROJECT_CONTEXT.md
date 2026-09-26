# Project context

The goal is a Home Assistant integration that reacts to live SHL games,
particularly Skellefteå AIK goals.

The legacy SHL Open API was investigated and rejected as the target. The current
SHL website exposes first-party REST APIs. The useful architecture is:

SHL schedule -> game discovery -> active game -> game-info + play-by-play ->
normalized models -> HA coordinator -> entities/events -> automations.

A historical SAIK vs Luleå playoff game demonstrated that play-by-play goal
events contain scoring team/player, assists, score-after-event, period, game
time, power-play status, penalty-shot/empty-net flags and event revision.

Idempotency is essential: polling must not repeatedly trigger the same goal.

The v0.1.0 code is a prototype; game discovery and the complete live pipeline
remain to be implemented.

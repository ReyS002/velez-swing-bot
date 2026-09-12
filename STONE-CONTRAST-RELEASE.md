# Sovereign 1.9.0 — stone contrast

New York, Tokyo, Hawaii and Dubai receive the approved stone colors in both lighting modes. Executive retains its existing artwork.

The eight `bot/static/dashboard/sovereign/stone-*-clean.png` assets were created with the built-in image-generation tool from existing spacing artwork and approved color references. Prompts requested stone-only recoloring: slate gray for New York, ash gray with blue undertones for Tokyo, pale sandy limestone for Hawaii, and medium taupe gray for Dubai, preserving lighting and object geometry.

Production uses these as clipped stone textures, not replacement room plates. `sovereign-stone.js` preserves original skies, shelves, leather and object artwork underneath masks. Existing statue contours protect the bull and bear. Room preloading includes the new layer, and the same room import version is used by both dashboard and broadcast. Mobile artwork is centered consistently with the room coordinates.

Local validation: 30 frontend checks passed; 30 room/lighting states loaded across three bots; responsive alignment at 1920×1080 and 390×844 passed; Vault remains clickable; 42 TV room/theme transitions passed with maximum corner error 0.00453 pixels. Day/night screenshots visually reviewed for all four changed rooms.

Deployment uses clean detached revisions and image-only Compose overrides. Trading configuration, credentials, broker settings and data mounts are preserved.

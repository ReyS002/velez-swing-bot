# Velez Bot Dashboard V4.6

Dashboard V4.6 moves the command room to the selected Candidate C background and adds a paired daylight room for light mode. Both rooms share the same monitor, journal, iPod, calendar, safe, command center, and Jarvis hotspot map.

## URL

Local:

```text
http://127.0.0.1:8080/dashboard
```

VPS:

```text
https://velezbot.72.62.169.3.nip.io/dashboard
```

## V4.6 Upgrades

- Replaced the V4/V4.5 room with the selected Candidate C night command room
- Added a generated daytime sibling for light mode
- Added a day/night toggle in the status bar
- Mapped the live chart canvas into the real monitor screen
- Remapped invisible hotspots to Candidate C objects: monitor, keyboard/command center, journal, calendar, safe, iPod/music player, and Jarvis shelf zone
- Kept mobile simple with the bottom icon rail and no image hotspots

## Assets

```text
bot/static/dashboard/v46-room-night.png
bot/static/dashboard/v46-room-day.png
```

## Notes

The theme choice is saved in browser local storage. The dashboard remains read-only and never exposes Alpaca API keys, Alpaca secret keys, or the TradingView webhook secret.

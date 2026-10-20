# IPTV US English

US English channels from the iptv-org playlist, with an XMLTV guide rebuilt daily from the free
[matthuisman/i.mjh.nz](https://github.com/matthuisman/i.mjh.nz) guides (Pluto TV, Samsung TV Plus, Plex, Roku, PBS).

## Links for your player
Replace `dl3nnox/iptv-us-english` with this repo's path.

| What | Link |
|---|---|
| Playlist – channels with guide | `https://raw.githubusercontent.com/dl3nnox/iptv-us-english/main/playlist_guide_only.m3u` |
| Playlist – all US English | `https://raw.githubusercontent.com/dl3nnox/iptv-us-english/main/playlist_all.m3u` |
| EPG (XMLTV) | `https://raw.githubusercontent.com/dl3nnox/iptv-us-english/main/epg.xml.gz` |

The playlists already include the EPG link, so most players pick up the guide automatically.

## Stream health
Every day each stream is tested from GitHub's US servers. Streams that fail 2 days in a row are hidden from the playlists (and come back automatically if they recover); when a channel has several copies, the fastest is listed first. See [STREAM_HEALTH.md](STREAM_HEALTH.md) for slow and failing channels.

## How it works
`.github/workflows/build-epg.yml` runs `scripts/build_epg.py` every day and commits fresh files.
Run it by hand from the **Actions** tab → **Build EPG** → **Run workflow**.
To change the channel list, edit `source/us_english_all.m3u`.

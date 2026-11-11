# CrateMatch

Turns a client's song request list (a Spotify playlist, a pasted list, or a .txt / .csv / Word file)
into a **VirtualDJ playlist** built from the music the DJ already has. Nothing is downloaded, and no
music files are moved or changed.

- Reads VirtualDJ's own library (`database.xml` in the VirtualDJ home folder and on each drive) plus
  any extra music folders. Works with MP3, WAV (tagged or not), M4A, FLAC, AIFF and more.
- Fuzzy matching copes with messy file names, "Title - Artist" order, typos, feat. credits, and
  clean / dirty / radio edit / intro versions. A remix request only matches that remix.
- Writes the list the way VirtualDJ 8.5 does (`MyLists\<name>.vdjfolder` + the `order` file), so it
  shows under **My Lists**.
- Spotify: sign in to pick from your playlists (full length for playlists you own), or paste any
  public playlist link (first 100 songs).
- Updates itself from this repo's Releases.

## Download

Get `CrateMatchSetup.exe` from [Releases](../../releases/latest).

## Developing

```
python -m pip install -r requirements.txt
python run.py                       # run from source
python tests\test_match.py          # matcher checks
python tests\test_sources.py        # list parsing
python tests\make_test_library.py   # then: python tests\test_end_to_end.py
```

- `Build Installer.bat` builds `dist\CrateMatch.exe` (PyInstaller) and `installer\Output\CrateMatchSetup.exe` (Inno Setup).
- `Publish Update.bat` bumps the version, builds, pushes, and makes a GitHub release. Installed copies
  update the next time they open.
- Spotify sign-in uses a Spotify developer app (PKCE, no secret). Its Client ID goes in
  `cratematch/spotify_auth.py` (`DEFAULT_CLIENT_ID`); redirect URI `http://127.0.0.1:43821/callback`.
  Development Mode allows 5 users, who must be added under User Management.

### Letting someone use Spotify sign-in

When a new person signs in, CrateMatch tells them their account "isn't on the list yet" and helps them
send you their Spotify email. To add them: [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
→ CrateMatch → **User Management** → their full name and Spotify email → **Add user**. They then click
**Sign in with Spotify** again. (Max 5 people; the app owner is always allowed.)

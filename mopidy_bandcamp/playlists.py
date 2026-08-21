from mopidy import backend
from mopidy.models import Playlist, Ref

from mopidy_bandcamp import logger


class BandcampPlaylistsProvider(backend.PlaylistsProvider):
    """Read-only playlists mirroring the fan account's Collection and
    Wishlist.

    Bandcamp has no first-class playlist API; the collection endpoints power
    the library browse tree. Surfacing the same data through Mopidy's
    playlists API lets playlist-oriented clients see Bandcamp content
    without walking the browse tree.

    Albums in the collection are expanded to their tracks via the library
    provider (one scrape per album), so expansion is capped to keep playlist
    listing bounded on large collections.
    """

    # Hard caps so a huge collection can't turn one playlist open into
    # hundreds of scrapes / thousands of tracks.
    MAX_ALBUM_EXPANSIONS = 40
    MAX_TRACKS = 400

    URI_COLLECTION = "bandcamp:playlist:collection"
    URI_WISHLIST = "bandcamp:playlist:wishlist"

    def __init__(self, backend):
        super().__init__(backend)
        # Playlist-tile artwork: first collection item's art id per
        # playlist uri, served through the library's get_images.
        self._art_by_uri = {}

    def _enabled(self):
        return bool(self.backend.bandcamp.identity)

    def playlist_art(self, uri):
        """Art id (f4.bcbits.com token) for a playlist uri, fetching the
        first (disk-cached) collection page on demand so the Playlists tab
        shows real artwork instead of placeholders."""
        colltype = self._colltype(uri)
        if colltype is None or not self._enabled():
            return None
        if uri in self._art_by_uri:
            return self._art_by_uri[uri]
        art = None
        try:
            data = self.backend.bandcamp.get_collection(ctype=colltype)
            for item in data.get("items", []):
                item_art = item.get("item_art") or {}
                if item_art.get("art_id"):
                    art = f"a{item_art['art_id']:010d}"
                    break
        except Exception:
            logger.exception("Bandcamp playlist art fetch failed")
        self._art_by_uri[uri] = art
        return art

    def as_list(self):
        if not self._enabled():
            return []
        return [
            Ref.playlist(uri=self.URI_COLLECTION, name="Bandcamp Collection"),
            Ref.playlist(uri=self.URI_WISHLIST, name="Bandcamp Wishlist"),
        ]

    def _colltype(self, uri):
        if uri == self.URI_COLLECTION:
            return "collection"
        if uri == self.URI_WISHLIST:
            return "wishlist"
        return None

    def _collect_tracks(self, colltype):
        """Expand the collection/wishlist into Track models via the library
        provider (which caches lookups and scrape URLs)."""
        library = self.backend.library
        tracks = []
        albums_expanded = 0
        token = None
        while True:
            try:
                data = self.backend.bandcamp.get_collection(
                    token=token, ctype=colltype
                )
            except Exception:
                logger.exception("Bandcamp playlist: collection fetch failed")
                break
            if not data or "items" not in data:
                break
            uri_key = (
                self.URI_COLLECTION
                if colltype == "collection"
                else self.URI_WISHLIST
            )
            for item in data["items"]:
                item_art = item.get("item_art") or {}
                if uri_key not in self._art_by_uri and item_art.get("art_id"):
                    self._art_by_uri[uri_key] = f"a{item_art['art_id']:010d}"
                if len(tracks) >= self.MAX_TRACKS:
                    logger.info(
                        "Bandcamp playlist: capped at %d tracks",
                        self.MAX_TRACKS,
                    )
                    return tracks
                prefix = "my" if colltype == "collection" else ""
                if item["tralbum_type"] == "a":
                    if albums_expanded >= self.MAX_ALBUM_EXPANSIONS:
                        continue
                    albums_expanded += 1
                    album_id = "{}-{}".format(item["band_id"], item["album_id"])
                    uri = "bandcamp:{}album:{}".format(prefix, album_id)
                    if prefix and "item_url" in item:
                        library.scrape_urls[uri] = item["item_url"]
                    try:
                        tracks.extend(library.lookup(uri))
                    except Exception:
                        logger.exception(
                            "Bandcamp playlist: album expansion failed for %s",
                            uri,
                        )
                elif item["tralbum_type"] == "t":
                    album_id = item["album_id"] if item["album_id"] else 0
                    track_id = "{}-{}-{}".format(
                        item["band_id"], album_id, item["item_id"]
                    )
                    uri = "bandcamp:{}track:{}".format(prefix, track_id)
                    if prefix and "item_url" in item:
                        library.scrape_urls[uri] = item["item_url"]
                    try:
                        tracks.extend(library.lookup(uri))
                    except Exception:
                        logger.exception(
                            "Bandcamp playlist: track lookup failed for %s",
                            uri,
                        )
            if data.get("more_available") and len(tracks) < self.MAX_TRACKS:
                token = data.get("last_token")
            else:
                break
        return tracks

    def get_items(self, uri):
        colltype = self._colltype(uri)
        if colltype is None or not self._enabled():
            return None
        return [
            Ref.track(uri=t.uri, name=t.name)
            for t in self._collect_tracks(colltype)
        ]

    def lookup(self, uri):
        colltype = self._colltype(uri)
        if colltype is None or not self._enabled():
            return None
        name = (
            "Bandcamp Collection"
            if colltype == "collection"
            else "Bandcamp Wishlist"
        )
        return Playlist(uri=uri, name=name, tracks=self._collect_tracks(colltype))

    def refresh(self):
        # Collection data is fetched on demand; nothing cached here.
        pass

    # Bandcamp playlists are read-only mirrors of the fan account.
    def create(self, name):
        return None

    def delete(self, uri):
        return False

    def save(self, playlist):
        return None

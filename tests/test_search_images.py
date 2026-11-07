from unittest import mock

from mopidy_bandcamp import backend as backend_lib

from tests import test_extension

# The shape of a fuzzysearch app_autocomplete answer: one album, one artist
# (band) and one track, with the image fields Bandcamp returns for each.
SEARCH_RESPONSE = {
    "results": [
        {
            "type": "a",
            "id": 1033878726,
            "band_id": 3724481684,
            "band_name": "Trainwreck Riders",
            "name": "Trainwreck Riders",
            "art_id": 3795786584,
            "img_id": None,
        },
        {
            "type": "b",
            "id": 3724481684,
            "name": "Trainwreck Riders",
            "art_id": None,
            "img_id": 17597512,
        },
        {
            "type": "t",
            "id": 1635069978,
            "album_id": 2845443263,
            "album_name": "Ghost Yards",
            "band_id": 3724481684,
            "band_name": "Trainwreck Riders",
            "name": "Silver Wings",
            "art_id": 2033105375,
            "img_id": None,
        },
    ]
}


def _library():
    backend = backend_lib.BandcampBackend(test_extension.ExtensionTest.get_config(), None)
    backend.bandcamp.search = mock.Mock(return_value=SEARCH_RESPONSE)
    return backend.library


def _first_image(library, uri):
    images = library.get_images([uri])[uri]
    return images[0].uri if images else None


def test_search_results_have_artwork():
    library = _library()
    result = library.search(query={"any": ["trainwreck riders"]})

    assert len(result.albums) == 1
    assert len(result.artists) == 1
    assert len(result.tracks) == 1

    album_uri = "bandcamp:album:3724481684-1033878726"
    artist_uri = "bandcamp:artist:3724481684"
    track_uri = "bandcamp:track:3724481684-2845443263-1635069978"

    assert _first_image(library, album_uri) == (
        "https://f4.bcbits.com/img/a3795786584_10.jpg"
    )
    assert _first_image(library, artist_uri) == (
        "https://f4.bcbits.com/img/0017597512_10.jpg"
    )
    assert _first_image(library, track_uri) == (
        "https://f4.bcbits.com/img/a2033105375_10.jpg"
    )


def test_a_track_result_gives_its_album_a_cover():
    library = _library()
    library.search(query={"any": ["trainwreck riders"]})

    assert _first_image(library, "bandcamp:album:3724481684-2845443263") == (
        "https://f4.bcbits.com/img/a2033105375_10.jpg"
    )


def test_results_without_image_ids_get_no_artwork():
    library = _library()
    library.backend.bandcamp.search.return_value = {
        "results": [
            {
                "type": "a",
                "id": 1,
                "band_id": 2,
                "band_name": "x",
                "name": "y",
                "art_id": None,
                "img_id": None,
            },
            {"type": "b", "id": 3, "name": "z", "art_id": None, "img_id": None},
        ]
    }
    library.search(query={"any": ["x"]})

    assert library.get_images(["bandcamp:album:2-1"])["bandcamp:album:2-1"] == []
    assert library.get_images(["bandcamp:artist:3"])["bandcamp:artist:3"] == []

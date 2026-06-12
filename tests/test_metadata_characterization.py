from qobuz_dl import metadata


def test_metadata_title_formats_versions_and_classical_work_titles():
    assert metadata._get_title({"title": "Song", "version": "Live"}) == "Song (Live)"
    assert (
        metadata._get_title(
            {"work": "Symphony No. 5", "title": "I. Allegro", "version": "Live"}
        )
        == "Symphony No. 5: I. Allegro (Live)"
    )


def test_metadata_genre_normalization_preserves_first_seen_order_without_repeats():
    assert (
        metadata._format_genres(
            ["Pop/Rock", "Pop/Rock→Rock", "Pop/Rock→Rock→Alternatif et Indé"]
        )
        == "Pop, Rock, Alternatif et Indé"
    )


def test_metadata_copyright_replaces_qobuz_marker_text_with_symbols():
    assert metadata._format_copyright("(P) 2024 Label (C) 2024 Owner") == (
        "℗ 2024 Label © 2024 Owner"
    )
    assert metadata._format_copyright("") == ""

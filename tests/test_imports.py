from importlib import metadata


def test_package_exports_client_and_main():
    import qobuz_dl

    assert callable(qobuz_dl.main)
    assert qobuz_dl.Client is not None


def test_installed_package_metadata_exposes_cli_entry_points_and_dependency():
    dist = metadata.distribution("qobuz-dl")

    assert dist.metadata["Name"] == "qobuz-dl"
    assert "mutagen<2,>=1.47" in (dist.requires or [])

    console_scripts = {
        entry_point.name: entry_point.value
        for entry_point in dist.entry_points
        if entry_point.group == "console_scripts"
    }
    assert console_scripts["qobuz-dl"] == "qobuz_dl:main"
    assert console_scripts["qdl"] == "qobuz_dl:main"

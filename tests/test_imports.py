def test_package_exports_client_and_main():
    import qobuz_dl

    assert callable(qobuz_dl.main)
    assert qobuz_dl.Client is not None

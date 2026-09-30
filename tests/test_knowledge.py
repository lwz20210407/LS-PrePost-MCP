from ls_prepost_mcp.knowledge import list_capabilities, records, search_commands, search_knowledge


def test_sources_have_provenance_and_no_host_paths():
    items = records()
    assert len({r['id'] for r in items}) == len(items)
    assert any(r['id'] == 'library-cfile-support' for r in items)
    assert any(r['id'] == 'local-Example5' for r in items)
    for record in items:
        assert record['url'].startswith(('https://', 'local://'))
        assert record['integration']
        assert "\\Users\\" not in str(record)


def test_search_preserves_unverified_command_status():
    result = search_commands('runpython')
    assert result
    assert all(r['status'] == 'reference_unverified' for r in result)
    assert search_knowledge('DataCenter')


def test_capability_sources_are_resolvable():
    known = {r['id'] for r in records()}
    for capability in list_capabilities()['capabilities']:
        assert set(capability['sources']) <= known
        if capability['status'] != 'planned':
            assert capability.get('tool')

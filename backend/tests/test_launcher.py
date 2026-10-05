import pytest
from scripts.launch import private_address, main


@pytest.mark.parametrize('address', ['192.168.1.231', '10.0.0.5', '172.16.0.2'])
def test_launcher_accepts_private_network_addresses(address):
    assert private_address(address)


@pytest.mark.parametrize('address', ['127.0.0.1', '0.0.0.0', '8.8.8.8', '169.254.0.1', 'example.com', 'not-an-ip'])
def test_launcher_rejects_public_and_unusable_addresses(address):
    assert not private_address(address)


def test_phone_launcher_never_starts_second_server_over_existing_local_server(monkeypatch, capsys):
    from scripts import launch
    monkeypatch.setattr(launch.sys, 'argv', ['launch.py', '--lan', '--lan-address', '192.168.1.231', '--no-browser'])
    monkeypatch.setattr(launch, 'server_health', lambda: {'status': 'ok', 'lan_address': None})
    monkeypatch.setattr(launch.subprocess, 'Popen', lambda *args, **kwargs: pytest.fail('Must not start a second server'))
    assert main() == 1
    assert 'Ctrl+C' in capsys.readouterr().out

"""Start the installed local application and open it in the default browser."""
import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
import os
import socket
from ipaddress import IPv4Address, IPv4Network
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:8000'


def server_health():
    try:
        with urllib.request.urlopen(f'{URL}/api/health', timeout=1) as response:
            health = json.load(response)
        if (isinstance(health, dict) and health.get('status') == 'ok'
                and health.get('external_video_transfer') is False
                and 'model_ready' in health):
            return health
    except (OSError, ValueError, urllib.error.URLError):
        pass
    return None


def private_address(address):
    try:
        return any(IPv4Address(address) in IPv4Network(cidr) for cidr in
                   ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
    except ValueError:
        return False


def lan_address():
    candidates = []
    try:
        # UDP connect selects the default interface without sending a packet.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect(('8.8.8.8', 80))
            candidates.append(connection.getsockname()[0])
    except OSError:
        pass
    try:
        candidates.extend(item[4][0] for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    return next((address for address in candidates if private_address(address)), None)


def open_app(no_browser, phone_address=None):
    print(f'Кинема готова: {URL}', flush=True)
    if phone_address:
        print(f'На телефоне в той же Wi-Fi сети откройте: http://{phone_address}:8000', flush=True)
        print('Компьютер должен оставаться включённым. Используйте только доверенную сеть: вход без пароля.', flush=True)
    if not no_browser and not webbrowser.open(URL):
        print('Откройте этот адрес в браузере вручную.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-browser', action='store_true', help='Не открывать браузер')
    parser.add_argument('--lan', action='store_true', help='Разрешить доступ с телефона в одной Wi-Fi сети')
    parser.add_argument('--lan-address', help='Указать частный IPv4 адрес Wi-Fi вручную (вместе с --lan)')
    args = parser.parse_args()
    if args.lan_address and (not args.lan or not private_address(args.lan_address)):
        parser.error('--lan-address требует --lan и частный IPv4 адрес')
    address = (args.lan_address or lan_address()) if args.lan else None
    if args.lan and not address:
        print('Не найден адрес локальной сети. Подключите компьютер к Wi-Fi или укажите --lan-address.')
        return 1
    existing = server_health()
    if existing:
        if args.lan and existing.get('lan_address') != address:
            print('Сервер уже работает в другом режиме. Остановите его (Ctrl+C в окне запуска) и повторите запуск для телефона.')
            return 1
        open_app(args.no_browser, existing.get('lan_address'))
        return 0
    if not (ROOT / 'frontend/dist/index.html').is_file():
        print('Сначала соберите интерфейс: cd frontend, затем npm run build.')
        return 1
    print('Запускаю Кинему… Оставьте это окно открытым. Для остановки нажмите Ctrl+C.', flush=True)
    environment = os.environ.copy()
    environment['KINEMA_LAN_ADDRESS'] = address or ''
    process = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'backend.app.main:app',
         '--host', '0.0.0.0' if args.lan else '127.0.0.1', '--port', '8000'], cwd=ROOT, env=environment,
    )
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                print('Сервер не запустился. Проверьте сообщение об ошибке выше.')
                return 1
            if server_health():
                open_app(args.no_browser, address)
                return process.wait()
            time.sleep(0.5)
        print('Сервер не стал доступен за 60 секунд. Проверьте сообщения выше.')
        return 1
    except KeyboardInterrupt:
        print('\nОстанавливаю Кинему…', flush=True)
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    raise SystemExit(main())

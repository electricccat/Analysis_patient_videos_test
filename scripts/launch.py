"""Start the installed local application and open it in the default browser."""
import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:8000'


def is_ready():
    try:
        with urllib.request.urlopen(f'{URL}/api/health', timeout=1) as response:
            health = json.load(response)
        return (isinstance(health, dict) and health.get('status') == 'ok'
                and health.get('external_video_transfer') is False
                and 'model_ready' in health)
    except (OSError, ValueError, urllib.error.URLError):
        return False


def open_app(no_browser):
    print(f'Кинема готова: {URL}', flush=True)
    if not no_browser and not webbrowser.open(URL):
        print('Откройте этот адрес в браузере вручную.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-browser', action='store_true', help='Не открывать браузер')
    args = parser.parse_args()
    if is_ready():
        open_app(args.no_browser)
        return 0
    if not (ROOT / 'frontend/dist/index.html').is_file():
        print('Сначала соберите интерфейс: cd frontend, затем npm run build.')
        return 1
    print('Запускаю Кинему… Оставьте это окно открытым. Для остановки нажмите Ctrl+C.', flush=True)
    process = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'backend.app.main:app',
         '--host', '127.0.0.1', '--port', '8000'], cwd=ROOT,
    )
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                print('Сервер не запустился. Проверьте сообщение об ошибке выше.')
                return 1
            if is_ready():
                open_app(args.no_browser)
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

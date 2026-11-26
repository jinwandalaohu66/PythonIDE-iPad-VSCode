"""Run in PythonIDE on iPad. Install a compatible official release and open the local workbench offline."""

from contextlib import contextmanager
import ctypes
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import re
import runpy
import stat
import sys
import tempfile
from urllib.error import URLError
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile


CHANNEL_FORMAT = 1
MIN_HOST = "1.8.5"
FACTORY_MAIN_021 = "6540dd405ea3ff5ac2f8201a3a0da52b24e043329da33cefcd2807544da8e643"
REPO = "jinwandalaohu66/PythonIDE-iPad-VSCode"
FOLDER = "PythonIDEWorkbench"
ASSET = FOLDER + ".zip"
API = f"https://api.github.com/repos/{REPO}"
CHANNEL = "releases.json"
MAX_DOWNLOAD = 64 * 1024 * 1024
NETWORK_ERRORS = (URLError, TimeoutError, ConnectionError, http.client.HTTPException)

TEXT = {
    "en": {
        "modified": "Your original main.py has been edited. Keep this installation and install the newer release in a separate folder.",
        "incompatible": "No release supports this version of PythonIDE.",
        "check": "Check for Updates",
        "offline": "Open Offline",
        "older": "This installation predates in-workbench updates. Check GitHub now or open your installed version.",
        "download": "Downloading workbench {version} from GitHub…",
        "progress": "Downloaded {percent}%",
        "open": "Opening the local workbench…",
        "network": "Couldn’t download the workbench. Check your connection and run this script again.",
        "integrity": "The download did not match this release. Run this script again to download a fresh copy.",
        "conflict": "The local PythonIDEWorkbench folder is incomplete or belongs to another project. Rename it before trying again.",
        "storage": "Couldn’t save the workbench. Check the available space in your local workspace and try again.",
        "host": "Open this script in PythonIDE on iPad and tap Run."
    },
    "zh-Hans": {
        "modified": "原来的 main.py 已被修改。请保留这份工作台，将新版单独安装到另一个文件夹。",
        "incompatible": "当前 PythonIDE 版本没有兼容的工作台发行版。",
        "check": "检查更新",
        "offline": "离线打开",
        "older": "此版本还没有工作台内更新菜单。可以现在检查 GitHub，也可以直接打开已安装的版本。",
        "download": "正在从 GitHub 下载工作台 {version}…",
        "progress": "已下载 {percent}%",
        "open": "正在打开本地工作台…",
        "network": "未能下载工作台。请检查网络后重新运行本脚本。",
        "integrity": "下载文件与发行版本不符。请重新运行本脚本下载完整文件。",
        "conflict": "本地 PythonIDEWorkbench 文件夹不完整或属于其他项目。请将它改名后再试。",
        "storage": "无法保存工作台。请检查本地工作区的可用空间后再试。",
        "host": "请在 iPad 的 PythonIDE 中打开此脚本并点运行。"
    },
    "zh-Hant": {
        "modified": "原本的 main.py 已經修改。請保留這份工作台，將新版另行安裝至其他資料夾。",
        "incompatible": "此 PythonIDE 版本沒有相容的工作台版本。",
        "check": "檢查更新",
        "offline": "離線開啟",
        "older": "此版本尚未提供工作台內的更新選單。你可以立即檢查 GitHub，或直接開啟已安裝的版本。",
        "download": "正在從 GitHub 下載工作台 {version}…",
        "progress": "已下載 {percent}%",
        "open": "正在開啟本機工作台…",
        "network": "無法下載工作台。請檢查網路連線後再次執行此指令稿。",
        "integrity": "下載的檔案與發行版本不符。請再次執行此指令稿，重新下載完整檔案。",
        "conflict": "本機的 PythonIDEWorkbench 資料夾不完整，或屬於其他專案。請將它重新命名後再試。",
        "storage": "無法儲存工作台。請檢查本機工作區的可用空間後再試。",
        "host": "請在 iPad 的 PythonIDE 中開啟此指令稿並點選執行。"
    },
    "de": {
        "modified": "Deine ursprüngliche main.py wurde bearbeitet. Behalte diese Installation und installiere die neue Version in einem separaten Ordner.",
        "incompatible": "Für diese PythonIDE-Version ist kein kompatibles Release verfügbar.",
        "check": "Nach Updates suchen",
        "offline": "Offline öffnen",
        "older": "Diese Version hat noch kein Update-Menü. Suche auf GitHub nach Updates oder öffne die installierte Version.",
        "download": "Arbeitsumgebung {version} wird von GitHub geladen…",
        "progress": "{percent} % heruntergeladen",
        "open": "Lokale Arbeitsumgebung wird geöffnet…",
        "network": "Download fehlgeschlagen. Prüfe die Internetverbindung und führe das Skript erneut aus.",
        "integrity": "Die Datei stimmt nicht mit dieser Version überein. Führe das Skript für einen neuen Download erneut aus.",
        "conflict": "Der lokale Ordner PythonIDEWorkbench ist unvollständig oder gehört zu einem anderen Projekt. Benenne ihn um und versuche es erneut.",
        "storage": "Die Arbeitsumgebung konnte nicht gespeichert werden. Prüfe den freien Speicherplatz und versuche es erneut.",
        "host": "Öffne dieses Skript in PythonIDE auf dem iPad und tippe auf Ausführen."
    },
    "es": {
        "modified": "El archivo main.py original se ha modificado. Conserva esta instalación e instala la versión nueva en otra carpeta.",
        "incompatible": "No hay una edición compatible con esta versión de PythonIDE.",
        "check": "Buscar actualizaciones",
        "offline": "Abrir sin conexión",
        "older": "Esta versión aún no tiene menú de actualizaciones. Busca una versión en GitHub o abre la que tienes instalada.",
        "download": "Descargando el entorno {version} desde GitHub…",
        "progress": "Descarga al {percent} %",
        "open": "Abriendo el entorno local…",
        "network": "No se ha podido descargar el entorno. Comprueba la conexión y vuelve a ejecutar el script.",
        "integrity": "El archivo no coincide con esta versión. Vuelve a ejecutar el script para descargarlo de nuevo.",
        "conflict": "La carpeta local PythonIDEWorkbench está incompleta o pertenece a otro proyecto. Cámbiale el nombre y vuelve a intentarlo.",
        "storage": "No se ha podido guardar el entorno. Comprueba el espacio disponible y vuelve a intentarlo.",
        "host": "Abre este script en PythonIDE en el iPad y toca Ejecutar."
    },
    "fr": {
        "modified": "Le fichier main.py d’origine a été modifié. Conservez cette installation et placez la nouvelle version dans un autre dossier.",
        "incompatible": "Aucune version de l’atelier n’est compatible avec cette version de PythonIDE.",
        "check": "Rechercher une mise à jour",
        "offline": "Ouvrir hors ligne",
        "older": "Cette version ne propose pas encore de menu de mise à jour. Vérifiez sur GitHub ou ouvrez la version installée.",
        "download": "Téléchargement de l’atelier {version} depuis GitHub…",
        "progress": "{percent} % téléchargés",
        "open": "Ouverture de l’atelier local…",
        "network": "Impossible de télécharger l’atelier. Vérifiez la connexion et relancez ce script.",
        "integrity": "Le fichier téléchargé ne correspond pas à cette version. Relancez le script pour le télécharger à nouveau.",
        "conflict": "Le dossier local PythonIDEWorkbench est incomplet ou appartient à un autre projet. Renommez-le, puis réessayez.",
        "storage": "Impossible d’enregistrer l’atelier. Vérifiez l’espace libre, puis réessayez.",
        "host": "Ouvrez ce script dans PythonIDE sur iPad et touchez Exécuter."
    },
    "ja": {
        "modified": "元の main.py が変更されています。この環境を残し、新しいバージョンを別のフォルダにインストールしてください。",
        "incompatible": "この PythonIDE に対応するリリースがありません。",
        "check": "アップデートを確認",
        "offline": "オフラインで開く",
        "older": "このバージョンには更新メニューがありません。GitHub で更新を確認するか、インストール済みのバージョンを開けます。",
        "download": "GitHub からワークベンチ {version}をダウンロード中…",
        "progress": "{percent}% ダウンロード済み",
        "open": "ローカルのワークベンチを開いています…",
        "network": "ダウンロードできませんでした。ネットワーク接続を確認し、このスクリプトをもう一度実行してください。",
        "integrity": "ダウンロードしたファイルがこのリリースと一致しません。スクリプトをもう一度実行してダウンロードし直してください。",
        "conflict": "ローカルの PythonIDEWorkbench フォルダが不完全か、別のプロジェクトで使用されています。フォルダ名を変更してからやり直してください。",
        "storage": "保存できませんでした。ローカルワークスペースの空き容量を確認してからやり直してください。",
        "host": "iPad の PythonIDE でこのスクリプトを開き、実行をタップしてください。"
    },
    "ko": {
        "modified": "원래 main.py 파일이 수정되었습니다. 이 설치본을 보관하고 새 버전은 다른 폴더에 설치하세요.",
        "incompatible": "이 PythonIDE 버전과 호환되는 릴리스가 없습니다.",
        "check": "업데이트 확인",
        "offline": "오프라인으로 열기",
        "older": "설치된 버전에는 업데이트 메뉴가 없습니다. GitHub에서 업데이트를 확인하거나 현재 버전을 여세요.",
        "download": "GitHub에서 워크벤치 {version} 다운로드 중…",
        "progress": "{percent}% 다운로드됨",
        "open": "로컬 워크벤치를 여는 중…",
        "network": "워크벤치를 다운로드하지 못했습니다. 네트워크 연결을 확인한 후 스크립트를 다시 실행하세요.",
        "integrity": "다운로드한 파일이 이 릴리스와 일치하지 않습니다. 스크립트를 다시 실행해 파일을 새로 받으세요.",
        "conflict": "로컬 PythonIDEWorkbench 폴더가 불완전하거나 다른 프로젝트에서 사용 중입니다. 폴더 이름을 변경한 후 다시 시도하세요.",
        "storage": "워크벤치를 저장할 수 없습니다. 로컬 작업 공간의 여유 용량을 확인한 후 다시 시도하세요.",
        "host": "iPad의 PythonIDE에서 이 스크립트를 열고 실행을 누르세요."
    },
    "pt-BR": {
        "modified": "O arquivo main.py original foi editado. Mantenha esta instalação e instale a nova versão em outra pasta.",
        "incompatible": "Nenhuma versão do ambiente é compatível com esta versão do PythonIDE.",
        "check": "Verificar atualizações",
        "offline": "Abrir offline",
        "older": "Esta versão ainda não tem menu de atualizações. Consulte o GitHub ou abra a versão instalada.",
        "download": "Baixando o ambiente {version} do GitHub…",
        "progress": "Download em {percent}%",
        "open": "Abrindo o ambiente local…",
        "network": "Não foi possível baixar o ambiente. Verifique a conexão e execute o script novamente.",
        "integrity": "O arquivo baixado não corresponde a esta versão. Execute o script novamente para baixar uma nova cópia.",
        "conflict": "A pasta local PythonIDEWorkbench está incompleta ou pertence a outro projeto. Renomeie a pasta e tente novamente.",
        "storage": "Não foi possível salvar o ambiente. Verifique o espaço livre e tente novamente.",
        "host": "Abra este script no PythonIDE no iPad e toque em Executar."
    },
    "ru": {
        "modified": "Исходный файл main.py изменён. Сохраните эту копию и установите новую версию в отдельную папку.",
        "incompatible": "Для этой версии PythonIDE нет совместимого выпуска.",
        "check": "Проверить обновления",
        "offline": "Открыть без сети",
        "older": "В этой версии пока нет меню обновлений. Проверьте обновления на GitHub или откройте установленную версию.",
        "download": "Загрузка рабочей среды {version} с GitHub…",
        "progress": "Загружено {percent}%",
        "open": "Открытие локальной рабочей среды…",
        "network": "Не удалось загрузить рабочую среду. Проверьте соединение и запустите скрипт ещё раз.",
        "integrity": "Загруженный файл не соответствует этой версии. Запустите скрипт ещё раз, чтобы скачать файл заново.",
        "conflict": "Локальная папка PythonIDEWorkbench неполна или принадлежит другому проекту. Переименуйте её и повторите попытку.",
        "storage": "Не удалось сохранить рабочую среду. Проверьте свободное место и повторите попытку.",
        "host": "Откройте этот скрипт в PythonIDE на iPad и нажмите кнопку запуска."
    }
}


class InstallError(Exception):
    """The argument is a localized message key."""


def language(identifier):
    parts = identifier.replace("_", "-").lower().split("-")
    if parts[0] == "zh":
        traditional = "hant" in parts or ("hans" not in parts and any(x in parts for x in ("tw", "hk", "mo")))
        return "zh-Hant" if traditional else "zh-Hans"
    if parts[0] == "pt":
        return "pt-BR"
    return parts[0] if parts[0] in TEXT else "en"


def app_context():
    from objc_util import ObjCClass
    bundle = ObjCClass("NSBundle").mainBundle()
    preferred = bundle.preferredLocalizations().firstObject()
    manager = ObjCClass("NSFileManager").defaultManager()
    documents = manager.URLsForDirectory_inDomains_(9, 1).firstObject()
    return Path(str(documents.path())) / "Workspace", language(str(preferred))


def installed_entry(folder):
    if not os.path.lexists(folder):
        return None
    paths = ("main.py", "studio/server.py", "web/index.html", "client/package.json")
    if folder.is_dir() and not folder.is_symlink() and all(
        (folder / p).is_file() and (folder / p).resolve().is_relative_to(folder.resolve()) for p in paths
    ):
        try:
            manifest = json.loads((folder / "client/package.json").read_text(encoding="utf-8"))
            if isinstance(manifest, dict) and manifest.get("name") == "pythonide-workbench-client":
                return folder / "main.py"
        except (OSError, ValueError):
            pass
    raise InstallError("conflict")


def version_key(value):
    if not isinstance(value, str) or not re.fullmatch(r"(0|[1-9][0-9]{0,5})(\.(0|[1-9][0-9]{0,5})){2}", value):
        raise ValueError("Invalid release version")
    return tuple(map(int, value.split(".")))


def host_version():
    try:
        from objc_util import ObjCClass
        return str(ObjCClass("NSBundle").mainBundle().objectForInfoDictionaryKey_("CFBundleShortVersionString"))
    except ImportError:
        return MIN_HOST  # Desktop preview uses the oldest supported host contract.


def package_version(folder):
    return json.loads((folder / "client/package.json").read_text(encoding="utf-8"))["version"]


def open_url(url, accept):
    request = Request(url, headers={"Accept": accept, "User-Agent": "PythonIDE-WorkbenchInstaller/1"})
    return urlopen(request, timeout=20)


def asset_url(metadata, name):
    if metadata.get("draft") or metadata.get("prerelease"):
        return None
    for asset in metadata["assets"]:
        if asset["name"] == name and type(asset["id"]) is int:
            return f"{API}/releases/assets/{asset['id']}?download=1"
    return None


def latest_release(host):
    last_error = "network"
    for route in ("direct", "api"):
        try:
            url = f"https://github.com/{REPO}/releases/latest/download/{CHANNEL}"
            if route == "api":
                with open_url(API + "/releases/latest", "application/vnd.github+json") as response:
                    url = asset_url(json.loads(response.read(512 * 1024)), CHANNEL)
                if not url:
                    continue
            with open_url(url, "application/octet-stream") as response:
                raw = response.read(128 * 1024 + 1)
            if len(raw) > 128 * 1024:
                raise ValueError
            catalog = json.loads(raw)
            if catalog["schema"] != CHANNEL_FORMAT:
                raise ValueError
            supported = []
            for release in catalog["releases"]:
                version_key(release["version"])
                if (version_key(release["minHost"]) <= version_key(host)
                        and type(release["bytes"]) is int and 0 < release["bytes"] <= MAX_DOWNLOAD
                        and re.fullmatch(r"[0-9a-f]{64}", release["sha256"])):
                    supported.append(release)
            if supported:
                return max(supported, key=lambda r: version_key(r["version"]))
            raise InstallError("incompatible")
        except NETWORK_ERRORS:
            continue
        except (KeyError, AttributeError, TypeError, ValueError):
            last_error = "integrity"
            continue
    raise InstallError(last_error)


def download_urls(version):
    yield f"https://github.com/{REPO}/releases/download/v{version}/{ASSET}"
    with open_url(f"{API}/releases/tags/v{version}", "application/vnd.github+json") as response:
        metadata = json.loads(response.read(512 * 1024))
    if metadata.get("tag_name") != "v" + version or metadata.get("draft") or metadata.get("prerelease"):
        return
    fallback = asset_url(metadata, ASSET)
    if fallback:
        yield fallback


def fetch(target, release, strings):
    size = release["bytes"]
    last_error = "network"
    try:
        for url in download_urls(release["version"]):
            try:
                with open_url(url, "application/octet-stream") as response, target.open("wb") as stream:
                    digest = hashlib.sha256()
                    received = 0
                    next_update = 25
                    while block := response.read(64 * 1024):
                        received += len(block)
                        if received > size:
                            break
                        digest.update(block)
                        stream.write(block)
                        percent = received * 100 // size
                        if strings and percent >= next_update:
                            print(strings["progress"].format(percent=percent), flush=True)
                            next_update = (percent // 25 + 1) * 25
                    if received == size and digest.hexdigest() == release["sha256"]:
                        return
                    last_error = "integrity"
            except NETWORK_ERRORS:
                continue
    except (*NETWORK_ERRORS, KeyError, TypeError, ValueError):
        pass
    raise InstallError(last_error)


def publish(source, destination):
    if sys.platform in ("darwin", "ios"):
        # Darwin's exclusive rename publishes the entire verified folder without
        # replacing even an empty directory created by another app in the meantime.
        libc = ctypes.CDLL(None, use_errno=True)
        rename = libc.renamex_np
        rename.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        rename.restype = ctypes.c_int
        if rename(os.fsencode(source), os.fsencode(destination), 4) != 0:  # RENAME_EXCL
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(destination))
    else:
        if os.path.lexists(destination):
            raise FileExistsError(str(destination))
        source.rename(destination)


@contextmanager
def prepared(workspace, release, strings=None):
    workspace.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ipadvscode-", dir=workspace) as staging:
        staged = Path(staging)
        path = staged / ASSET
        fetch(path, release, strings)
        with ZipFile(path) as archive:
            members = archive.infolist()
            if len(members) > 12000 or sum(x.file_size for x in members) > 256 * 1024 * 1024:
                raise InstallError("integrity")
            seen = set()
            for member in members:
                name = PurePosixPath(member.filename)
                if (not name.parts or name.parts[0] != FOLDER or ".." in name.parts
                        or "\\" in member.filename or stat.S_ISLNK(member.external_attr >> 16)
                        or any(p.startswith(".workbench-") for p in name.parts) or name in seen):
                    raise InstallError("integrity")
                seen.add(name)
            archive.extractall(staged)
        program = staged / FOLDER
        if not installed_entry(program) or package_version(program) != release["version"]:
            raise InstallError("integrity")
        yield program


def ensure_installed(workspace, strings, host=None):
    destination = workspace / FOLDER
    entry = installed_entry(destination)
    if entry:
        return entry
    release = latest_release(host or host_version())
    print(strings["download"].format(version=release["version"]), flush=True)
    with prepared(workspace, release, strings) as program:
        try:
            publish(program, destination)
        except FileExistsError:
            if not installed_entry(destination):
                raise InstallError("conflict") from None
    return destination / "main.py"


def atomic_write(target, data):
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
        temp = Path(output.name)
        try:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
            output.close()
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)


def selected_version(home):
    base = package_version(home)
    store = home / ".workbench-updates"
    pointer = store / "current"
    if store.is_symlink() or pointer.is_symlink():
        raise InstallError("conflict")
    if pointer.exists():
        try:
            value = pointer.read_text(encoding="ascii").strip()
            version_key(value)
            program = store / value
            if installed_entry(program) and package_version(program) == value:
                return value
        except (ValueError, KeyError, InstallError):
            pass
    return base


@contextmanager
def update_lock(store):
    if store.is_symlink():
        raise InstallError("conflict")
    if os.name == "nt":
        import msvcrt
        marker = store / ".lock"
        if marker.is_symlink():
            raise InstallError("conflict")
        with marker.open("a+b") as handle:
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        descriptor = os.open(store, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)


def install_update(home, release, strings=None):
    home = home.resolve(strict=True)
    version = release["version"]
    if version_key(version) <= version_key(selected_version(home)):
        return
    with prepared(home.parent, release, strings) as program:
        store = home / ".workbench-updates"
        store.mkdir(exist_ok=True)
        with update_lock(store):
            if version_key(version) <= version_key(selected_version(home)):
                return
            entry = home / "main.py"
            migrate = version_key(selected_version(home)) < (0, 2, 2)
            # Only migrate the published 0.2.1 entry. An interrupted migration may already have written the dispatcher.
            main_bytes = (program / "main.py").read_bytes()
            if migrate:
                original = entry.read_bytes()
                if original != main_bytes and hashlib.sha256(original).hexdigest() != FACTORY_MAIN_021:
                    raise InstallError("modified")
            target = store / version
            if os.path.lexists(target):
                if not installed_entry(target) or any(
                        p.is_file() and (not (target / p.relative_to(program)).is_file()
                        or (target / p.relative_to(program)).resolve() != target / p.relative_to(program)
                        or (target / p.relative_to(program)).read_bytes() != p.read_bytes())
                        for p in program.rglob("*")):
                    raise InstallError("conflict")
            else:
                publish(program, target)
            if migrate and hashlib.sha256(entry.read_bytes()).hexdigest() == FACTORY_MAIN_021:
                atomic_write(entry, main_bytes)
            atomic_write(store / "current", version.encode("ascii"))


def main():
    try:
        workspace, code = app_context()
    except ImportError:
        raise SystemExit(TEXT["en"]["host"]) from None
    strings = TEXT[code]
    try:
        entry = ensure_installed(workspace, strings)
        home = entry.parent
        explicit = "--update" in sys.argv[1:]
        previous = version_key(selected_version(home))
        if not explicit and previous < (0, 2, 2):
            offered = home / ".workbench-update-offered"
            if not os.path.lexists(offered):
                import console
                explicit = console.alert("iPad VSCode", strings["older"], button1=strings["check"],
                                         button2=strings["offline"], hide_cancel_button=True) == 1
                offered.touch(exist_ok=True)
        if explicit:
            try:
                install_update(home, latest_release(host_version()), strings)
            except (OSError, BadZipFile, InstallError, ValueError) as error:
                key = error.args[0] if isinstance(error, InstallError) else "storage"
                print(strings.get(key, strings["integrity"]), file=sys.stderr, flush=True)
    except (InstallError, OSError, BadZipFile, ValueError) as error:
        key = error.args[0] if isinstance(error, InstallError) else (
            "integrity" if isinstance(error, BadZipFile) else "storage")
        print(strings[key], file=sys.stderr, flush=True)
        raise SystemExit(1) from None
    print(strings["open"], flush=True)
    original = sys.argv
    try:
        sys.argv = [str(entry)]
        runpy.run_path(str(entry), run_name="__main__")
    finally:
        sys.argv = original


if __name__ == "__main__":
    main()

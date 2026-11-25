"""Run in PythonIDE on iPad. The first run installs the pinned GitHub release."""

import ctypes
import hashlib
import http.client
import json
import os
from pathlib import Path, PurePosixPath
import runpy
import stat
import sys
import tempfile
from urllib.error import URLError
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile


VERSION = "0.2.1"
REPO = "jinwandalaohu66/PythonIDE-iPad-VSCode"
FOLDER = "PythonIDEWorkbench"
ASSET = FOLDER + ".zip"
RELEASE = f"https://github.com/{REPO}/releases/download/v{VERSION}/{ASSET}"
API = f"https://api.github.com/repos/{REPO}/releases"
DOWNLOAD_BYTES = 4516562
SHA256 = "f0f78d1672c77dd9c134cebb848f8fdb1b47a152b3bdf45c71e7eb4a249cccfe"

TEXT = {
    "en": {
        "download": "Downloading workbench {version} from GitHub (4.3 MiB)…",
        "progress": "Downloaded {percent}%",
        "open": "Opening the local workbench…",
        "network": "Couldn’t download the workbench. Check your connection and run this script again.",
        "integrity": "The download did not match this release. Run this script again to download a fresh copy.",
        "conflict": "The local PythonIDEWorkbench folder is incomplete or belongs to another project. Rename it before trying again.",
        "storage": "Couldn’t save the workbench. Check the available space in your local workspace and try again.",
        "host": "Open this script in PythonIDE on iPad and tap Run."
    },
    "zh-Hans": {
        "download": "正在从 GitHub 下载工作台 {version}（约 4.3 MiB）…",
        "progress": "已下载 {percent}%",
        "open": "正在打开本地工作台…",
        "network": "未能下载工作台。请检查网络后重新运行本脚本。",
        "integrity": "下载文件与发行版本不符。请重新运行本脚本下载完整文件。",
        "conflict": "本地 PythonIDEWorkbench 文件夹不完整或属于其他项目。请将它改名后再试。",
        "storage": "无法保存工作台。请检查本地工作区的可用空间后再试。",
        "host": "请在 iPad 的 PythonIDE 中打开此脚本并点运行。"
    },
    "zh-Hant": {
        "download": "正在從 GitHub 下載工作台 {version}（約 4.3 MiB）…",
        "progress": "已下載 {percent}%",
        "open": "正在開啟本機工作台…",
        "network": "無法下載工作台。請檢查網路連線後再次執行此指令稿。",
        "integrity": "下載的檔案與發行版本不符。請再次執行此指令稿，重新下載完整檔案。",
        "conflict": "本機的 PythonIDEWorkbench 資料夾不完整，或屬於其他專案。請將它重新命名後再試。",
        "storage": "無法儲存工作台。請檢查本機工作區的可用空間後再試。",
        "host": "請在 iPad 的 PythonIDE 中開啟此指令稿並點選執行。"
    },
    "de": {
        "download": "Arbeitsumgebung {version} wird von GitHub geladen (4,3 MiB)…",
        "progress": "{percent} % heruntergeladen",
        "open": "Lokale Arbeitsumgebung wird geöffnet…",
        "network": "Download fehlgeschlagen. Prüfe die Internetverbindung und führe das Skript erneut aus.",
        "integrity": "Die Datei stimmt nicht mit dieser Version überein. Führe das Skript für einen neuen Download erneut aus.",
        "conflict": "Der lokale Ordner PythonIDEWorkbench ist unvollständig oder gehört zu einem anderen Projekt. Benenne ihn um und versuche es erneut.",
        "storage": "Die Arbeitsumgebung konnte nicht gespeichert werden. Prüfe den freien Speicherplatz und versuche es erneut.",
        "host": "Öffne dieses Skript in PythonIDE auf dem iPad und tippe auf Ausführen."
    },
    "es": {
        "download": "Descargando el entorno {version} desde GitHub (4,3 MiB)…",
        "progress": "Descarga al {percent} %",
        "open": "Abriendo el entorno local…",
        "network": "No se ha podido descargar el entorno. Comprueba la conexión y vuelve a ejecutar el script.",
        "integrity": "El archivo no coincide con esta versión. Vuelve a ejecutar el script para descargarlo de nuevo.",
        "conflict": "La carpeta local PythonIDEWorkbench está incompleta o pertenece a otro proyecto. Cámbiale el nombre y vuelve a intentarlo.",
        "storage": "No se ha podido guardar el entorno. Comprueba el espacio disponible y vuelve a intentarlo.",
        "host": "Abre este script en PythonIDE en el iPad y toca Ejecutar."
    },
    "fr": {
        "download": "Téléchargement de l’atelier {version} depuis GitHub (4,3 Mio)…",
        "progress": "{percent} % téléchargés",
        "open": "Ouverture de l’atelier local…",
        "network": "Impossible de télécharger l’atelier. Vérifiez la connexion et relancez ce script.",
        "integrity": "Le fichier téléchargé ne correspond pas à cette version. Relancez le script pour le télécharger à nouveau.",
        "conflict": "Le dossier local PythonIDEWorkbench est incomplet ou appartient à un autre projet. Renommez-le, puis réessayez.",
        "storage": "Impossible d’enregistrer l’atelier. Vérifiez l’espace libre, puis réessayez.",
        "host": "Ouvrez ce script dans PythonIDE sur iPad et touchez Exécuter."
    },
    "ja": {
        "download": "GitHub からワークベンチ {version}（約 4.3 MiB）をダウンロード中…",
        "progress": "{percent}% ダウンロード済み",
        "open": "ローカルのワークベンチを開いています…",
        "network": "ダウンロードできませんでした。ネットワーク接続を確認し、このスクリプトをもう一度実行してください。",
        "integrity": "ダウンロードしたファイルがこのリリースと一致しません。スクリプトをもう一度実行してダウンロードし直してください。",
        "conflict": "ローカルの PythonIDEWorkbench フォルダが不完全か、別のプロジェクトで使用されています。フォルダ名を変更してからやり直してください。",
        "storage": "保存できませんでした。ローカルワークスペースの空き容量を確認してからやり直してください。",
        "host": "iPad の PythonIDE でこのスクリプトを開き、実行をタップしてください。"
    },
    "ko": {
        "download": "GitHub에서 워크벤치 {version} 다운로드 중(약 4.3 MiB)…",
        "progress": "{percent}% 다운로드됨",
        "open": "로컬 워크벤치를 여는 중…",
        "network": "워크벤치를 다운로드하지 못했습니다. 네트워크 연결을 확인한 후 스크립트를 다시 실행하세요.",
        "integrity": "다운로드한 파일이 이 릴리스와 일치하지 않습니다. 스크립트를 다시 실행해 파일을 새로 받으세요.",
        "conflict": "로컬 PythonIDEWorkbench 폴더가 불완전하거나 다른 프로젝트에서 사용 중입니다. 폴더 이름을 변경한 후 다시 시도하세요.",
        "storage": "워크벤치를 저장할 수 없습니다. 로컬 작업 공간의 여유 용량을 확인한 후 다시 시도하세요.",
        "host": "iPad의 PythonIDE에서 이 스크립트를 열고 실행을 누르세요."
    },
    "pt-BR": {
        "download": "Baixando o ambiente {version} do GitHub (4,3 MiB)…",
        "progress": "Download em {percent}%",
        "open": "Abrindo o ambiente local…",
        "network": "Não foi possível baixar o ambiente. Verifique a conexão e execute o script novamente.",
        "integrity": "O arquivo baixado não corresponde a esta versão. Execute o script novamente para baixar uma nova cópia.",
        "conflict": "A pasta local PythonIDEWorkbench está incompleta ou pertence a outro projeto. Renomeie a pasta e tente novamente.",
        "storage": "Não foi possível salvar o ambiente. Verifique o espaço livre e tente novamente.",
        "host": "Abra este script no PythonIDE no iPad e toque em Executar."
    },
    "ru": {
        "download": "Загрузка рабочей среды {version} с GitHub (4,3 МиБ)…",
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


def open_url(url, accept):
    request = Request(url, headers={"Accept": accept, "User-Agent": "PythonIDE-iPadVSCode/" + VERSION})
    return urlopen(request, timeout=20)


def download_urls():
    yield RELEASE
    # Both routes are operated by GitHub. Some networks can reach only its API.
    with open_url(API + "/tags/v" + VERSION, "application/vnd.github+json") as response:
        metadata = json.loads(response.read(512 * 1024))
    for asset in metadata["assets"]:
        if asset["name"] == ASSET and type(asset["id"]) is int:
            yield f"{API}/assets/{asset['id']}?download=1"
            return


def fetch(target, strings):
    network_errors = (URLError, TimeoutError, ConnectionError, http.client.HTTPException)
    last_error = "network"
    try:
        for url in download_urls():
            try:
                with open_url(url, "application/octet-stream") as response, target.open("wb") as stream:
                    digest = hashlib.sha256()
                    received = 0
                    next_update = 25
                    while block := response.read(64 * 1024):
                        received += len(block)
                        if received > DOWNLOAD_BYTES:
                            break
                        digest.update(block)
                        stream.write(block)
                        percent = received * 100 // DOWNLOAD_BYTES
                        if percent >= next_update:
                            print(strings["progress"].format(percent=percent), flush=True)
                            next_update = (percent // 25 + 1) * 25
                    if received == DOWNLOAD_BYTES and digest.hexdigest() == SHA256:
                        return
                    last_error = "integrity"
            except network_errors:
                continue
    except (*network_errors, KeyError, TypeError, ValueError):
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


def ensure_installed(workspace, strings):
    destination = workspace / FOLDER
    entry = installed_entry(destination)
    if entry:
        return entry
    print(strings["download"].format(version=VERSION), flush=True)
    workspace.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ipadvscode-", dir=workspace) as staging:
        staged = Path(staging)
        archive_path = staged / ASSET
        fetch(archive_path, strings)
        with ZipFile(archive_path) as archive:
            for member in archive.infolist():
                path = PurePosixPath(member.filename)
                if (not path.parts or path.parts[0] != FOLDER or ".." in path.parts
                        or "\\" in member.filename or stat.S_ISLNK(member.external_attr >> 16)):
                    raise InstallError("integrity")
            archive.extractall(staged)
        if not installed_entry(staged / FOLDER):
            raise InstallError("integrity")
        try:
            publish(staged / FOLDER, destination)
        except FileExistsError:
            # Another invocation finished while this one downloaded.
            entry = installed_entry(destination)
            if entry is None:
                raise InstallError("conflict") from None
            return entry
    return destination / "main.py"


def main():
    try:
        workspace, code = app_context()
    except ImportError:
        raise SystemExit(TEXT["en"]["host"]) from None
    strings = TEXT[code]
    try:
        entry = ensure_installed(workspace, strings)
    except (InstallError, OSError, BadZipFile) as error:
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

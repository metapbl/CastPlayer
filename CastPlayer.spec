# PyInstaller onedir, 콘솔 창 없음 (D014, D043). 빌드: .venv\Scripts\pyinstaller.exe --noconfirm CastPlayer.spec
# ffmpeg·ffprobe는 넣지 않는다 (D042). config.json·logs·cache·bin은 exe 옆에 실행 중 생긴다.
import shutil

a = Analysis(['main.py'], datas=[('assets/cast.ico', 'assets')])   # 창 아이콘 (core.paths.asset_path)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='CastPlayer',
    console=False,
    icon='assets/cast.ico',   # exe 파일 아이콘 (D066)
)
coll = COLLECT(exe, a.binaries, a.datas, name='CastPlayer')

# 배포물에 라이선스·고지·설명을 exe 옆에 둔다 (MIT·LGPL 고지, D067)
for doc in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'README.md', 'README.en.md'):
    shutil.copy(doc, f'{DISTPATH}/CastPlayer/{doc}')

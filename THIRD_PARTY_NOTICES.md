# Third-party notices

CastPlayer는 MIT 라이선스입니다([LICENSE](LICENSE)). 실행 파일(Releases zip)에는 아래 구성 요소가 함께 들어 있고, 각 구성 요소는 자기 라이선스를 따릅니다.
CastPlayer is MIT-licensed ([LICENSE](LICENSE)). The executable (Releases zip) bundles the components below, each under its own license.

**ffmpeg와 ffprobe는 들어 있지 않습니다.** 사용자가 따로 설치합니다.
**ffmpeg and ffprobe are not included.** Users install them separately.

## Components

이 목록은 CastPlayer 1.0.0 빌드(PyInstaller 6.22.3, Python 3.15.1)에 실제로 들어간 것을 기준으로 합니다.
This list reflects what is actually bundled in the CastPlayer 1.0.0 build (PyInstaller 6.22.3, Python 3.15.1).

| Component | Version | License | Source |
|---|---|---|---|
| PySide6 (Qt for Python) and Qt 6 libraries | 6.12.0 | LGPL-3.0-only | https://pyside.org · https://code.qt.io |
| shiboken6 | 6.12.0 | LGPL-3.0-only | https://pyside.org |
| zeroconf | 0.151.5 | LGPL-2.1-or-later | https://github.com/python-zeroconf/python-zeroconf |
| PyChromecast | 14.0.10 | MIT | https://github.com/home-assistant-libs/pychromecast |
| protobuf | 7.36.2 | BSD-3-Clause | https://github.com/protocolbuffers/protobuf |
| ifaddr | 0.2.0 | MIT | https://github.com/pydron/ifaddr |
| requests | 2.34.2 | Apache-2.0 | https://github.com/psf/requests |
| urllib3 | 2.8.0 | MIT | https://github.com/urllib3/urllib3 |
| idna | 3.20 | BSD-3-Clause | https://github.com/kjd/idna |
| certifi | 2026.10.19 | MPL-2.0 | https://github.com/certifi/python-certifi |
| charset-normalizer | 3.5.2 | MIT | https://github.com/jawah/charset_normalizer |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | https://github.com/pypa/packaging |
| setuptools (pkg_resources, with its vendored packages) | 84.2.1 | MIT | https://github.com/pypa/setuptools |
| Python runtime and standard library | 3.15.1 | PSF-2.0 | https://www.python.org |
| OpenSSL (`libssl-3*.dll`, `libcrypto-3*.dll`, part of Python) | 3.5.9 | Apache-2.0 | https://www.openssl.org |
| libffi (`libffi-8.dll`, part of Python) | 3.x | MIT | https://github.com/libffi/libffi |
| Microsoft Visual C++ Runtime (`VCRUNTIME140*.dll`, `MSVCP140*.dll`) | 14.x | Microsoft Visual C++ Redistributable license | https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist |
| PyInstaller bootloader | 6.22.3 | GPL-2.0-or-later with bootloader exception | https://github.com/pyinstaller/pyinstaller |

Python에 함께 들어 있는 라이브러리(bzip2, xz/lzma, expat, mpdecimal, zstd 등)의 고지는 Python 라이선스 문서를 따릅니다: https://docs.python.org/3/license.html
Notices for libraries that ship with Python (bzip2, xz/lzma, expat, mpdecimal, zstd and others) are in the Python license document: https://docs.python.org/3/license.html

PyInstaller 부트로더 예외에 따라, 부트로더와 결합해 배포해도 CastPlayer에는 GPL이 적용되지 않습니다.
Under the PyInstaller bootloader exception, distributing CastPlayer with the bootloader does not place CastPlayer under the GPL.

## LGPL components (PySide6, Qt, shiboken6, zeroconf)

- 이 구성 요소들은 실행 파일 안에 합쳐 넣지 않고, `_internal\` 폴더에 별도 파일(Qt DLL, `.pyd`, 파이썬 모듈)로 들어 있습니다. 사용자는 같은 인터페이스의 수정 버전으로 바꿔 넣어 CastPlayer를 실행할 수 있습니다.
  These components are not merged into the executable. They are separate files (Qt DLLs, `.pyd` files, Python modules) in the `_internal\` folder, and users may replace them with modified versions that keep the same interface.
- CastPlayer의 소스 코드 전체는 이 저장소에 있으므로, 다른 버전의 라이브러리로 직접 빌드할 수도 있습니다 (`CastPlayer.spec`, README의 "소스에서 실행").
  The full CastPlayer source is in this repository, so you can also rebuild it against other library versions (`CastPlayer.spec`, "From source" in the README).
- 라이브러리 소스: Qt https://code.qt.io , PySide6·shiboken6 https://code.qt.io/cgit/pyside/pyside-setup.git , zeroconf https://github.com/python-zeroconf/python-zeroconf
  Library sources are at the links above.
- 라이선스 전문: LGPL-3.0 https://www.gnu.org/licenses/lgpl-3.0.html , LGPL-2.1 https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html , GPL-3.0(LGPL-3.0이 참조) https://www.gnu.org/licenses/gpl-3.0.html
  Full license texts are at the links above.

## Icon

`assets/cast.ico`는 CastPlayer 저장소 소유자가 제공한 것으로, CastPlayer와 함께 MIT 라이선스로 배포합니다.
`assets/cast.ico` was provided by the CastPlayer repository owner and is distributed with CastPlayer under the MIT License.

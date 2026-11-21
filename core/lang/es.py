"""es 사전 (AI 번역, D079). 키는 코드의 한국어 문장 (core/i18n.py). 순서는 en.py와 같음."""

STRINGS: dict[str, str] = {
    '{what} 실패: {err}':
        'Error en {what}: {err}',
    '연결된 기기가 없습니다.':
        'No hay ningún dispositivo conectado.',
    '기기 정보를 찾을 수 없습니다.':
        'No se encontró la información del dispositivo.',
    '자막 설정 응답 없음':
        'Sin respuesta al ajuste de subtítulos',
    'TV가 이 영상을 재생하지 못했습니다.':
        'El televisor no pudo reproducir este vídeo.',
    '연결 복구 중이라 {what} 명령을 보내지 못했습니다. 잠시 후 다시 시도하세요.':
        'Se está restableciendo la conexión, por lo que no se envió la orden {what}. Inténtelo de nuevo en un momento.',
    '연결 실패: {err}':
        'Error de conexión: {err}',
    '재생 요청':
        'solicitud de reproducción',
    '자막 설정':
        'ajuste de subtítulos',
    '수신 앱 종료':
        'cierre de la app receptora',
    '내부 오류: {err}':
        'Error interno: {err}',
    '볼륨 설정':
        'ajuste de volumen',
    '음소거':
        'silencio',
    '일시정지':
        'pausa',
    '재생':
        'reproducción',
    '이동':
        'búsqueda',
    'ffmpeg 실행 실패: {err}':
        'No se pudo ejecutar ffmpeg: {err}',
    '종료 코드 {rc}':
        'código de salida {rc}',
    '키프레임 분석 실패: {err}':
        'Falló el análisis de fotogramas clave: {err}',
    'ffprobe 실행 실패: {err}':
        'No se pudo ejecutar ffprobe: {err}',
    '키프레임 분석 실패 ({reached}/{duration}초에서 중단): {err}':
        'Falló el análisis de fotogramas clave (se detuvo en {reached}/{duration} s): {err}',
    '포트 {port}를 열 수 없습니다: {err}':
        'No se pudo abrir el puerto {port}: {err}',
    '재인코딩용 인코더가 없습니다.':
        'No hay ningún codificador para recodificar.',
    'ffmpeg 오류: {msg}':
        'Error de ffmpeg: {msg}',
    '영상 복사':
        'vídeo copiado',
    '영상 재인코딩':
        'vídeo recodificado',
    '음성 없음':
        'sin audio',
    '{codec} 코덱 미지원':
        'códec {codec} no compatible',
    '음성 트랙 #{n}이 없습니다.':
        'No existe la pista de audio n.º {n}.',
    '영상 트랙이 없습니다.':
        'No hay pista de vídeo.',
    '음성 {label} 복사':
        'audio {label} copiado',
    '음성 {label} → AAC 2ch':
        'audio {label} → AAC 2ch',
    '표시 시각 정보 없음(ctts 누락)':
        'sin marcas de tiempo de presentación (falta ctts)',
    '컨테이너 변환':
        'conversión de contenedor',
    'HEVC 태그 {tag}→hvc1':
        'etiqueta HEVC {tag}→hvc1',
    '기본 외 음성 트랙 선택':
        'pista de audio no predeterminada',
    'H.264 {profile} 미지원':
        'H.264 {profile} no compatible',
    'H.264 레벨 {level} 초과':
        'nivel H.264 superior a {level}',
    'HEVC {profile} 미지원':
        'HEVC {profile} no compatible',
    'HEVC 레벨 {level} 초과':
        'nivel HEVC superior a {level}',
    '4K H.264 한계로 {fps}fps':
        '{fps} fps por el límite de H.264 en 4K',
    '자막 추출':
        'Extrayendo subtítulos',
    '전체 길이를 알 수 없어 HLS로 보낼 수 없습니다.':
        'Se desconoce la duración total, por lo que no se puede enviar como HLS.',
    '사용 가능한 H.264 인코더가 없습니다.':
        'No hay ningún codificador H.264 disponible.',
    '불러온 파일이 없습니다.':
        'No hay ningún archivo cargado.',
    'HLS 준비가 되지 않았습니다.':
        'HLS no está listo.',
    '켜진 자막이 없습니다.':
        'No hay ningún subtítulo activado.',
    '키프레임 분석':
        'Analizando fotogramas clave',
    '자막 #{n}이 없습니다.':
        'No existe el subtítulo n.º {n}.',
    '자막 #{n}은 고를 수 없습니다 ({why}).':
        'No se puede elegir el subtítulo n.º {n} ({why}).',
    '내장#{n}':
        'Integrado n.º {n}',
    '(기본)':
        '(predeterminada)',
    '(지원 안 함)':
        '(no compatible)',
    'ffprobe 오류':
        'Error de ffprobe',
    'ffprobe 출력 해석 실패':
        'No se pudo leer la salida de ffprobe',
    '내장':
        'Integrado ',
    '{n}개':
        '{n} líneas',
    '지원 안 함':
        'no compatible',
    '읽기 실패':
        'error de lectura',
    '추출 실패':
        'error de extracción',
    '비어 있음':
        'vacío',
    '{names}을(를) 찾지 못했습니다.\n\n찾아본 곳:\n- {folder}\n- PATH 환경 변수\n\nPowerShell이나 명령 프롬프트에서 설치할 수 있습니다:\nwinget install Gyan.FFmpeg\n\n설치한 뒤 CastPlayer를 다시 실행해 주세요.':
        'No se encontró {names}.\n\nSe buscó en:\n- {folder}\n- la variable de entorno PATH\n\nPuede instalarlo desde PowerShell o el símbolo del sistema:\nwinget install Gyan.FFmpeg\n\nDespués de instalarlo, vuelva a ejecutar CastPlayer.',
    '로그 파일을 만들 수 없습니다: {path} ({err})':
        'No se pudo crear el archivo de registro: {path} ({err})',
    '{err}\n\nCastPlayer가 이미 실행 중이거나 다른 프로그램이 포트 {port}를 쓰고 있습니다.\nconfig.json의 server_port로 포트를 바꿀 수 있습니다.':
        '{err}\n\nCastPlayer ya se está ejecutando o otro programa está usando el puerto {port}.\nPuede cambiar el puerto con server_port en config.json.',
    '재생 / 일시정지':
        'Reproducir / Pausa',
    '볼륨 ±5%':
        'Volumen ±5%',
    '음소거 전환':
        'Activar/desactivar silencio',
    '정지 (TV 플레이어 종료)':
        'Detener (cierra el reproductor del televisor)',
    '파일 열기':
        'Abrir archivo',
    '기기 다시 찾기':
        'Buscar dispositivos de nuevo',
    '프로그램 종료':
        'Salir',
    'Shift+클릭':
        'Mayús+clic',
    '자막 싱크 버튼을 0.1초 단위로':
        'Botones de sincronía de subtítulos en pasos de 0,1 s',
    '지원 형식':
        'Formatos compatibles',
    '내장 텍스트 자막':
        'Subtítulos de texto incrustados',
    '그림 자막은 안 됨':
        'Los subtítulos de imagen no son compatibles',
    '그대로':
        'se mantiene',
    '등은 스테레오로 바꿈':
        'etc. se convierten a estéreo',
    '송출 방식':
        'Método de envío',
    '파일을 열면 자동으로 고름':
        'Se elige automáticamente al abrir un archivo',
    'mp4':
        'mp4',
    'H.264·HEVC 영상 + AAC·MP3 음성':
        'Vídeo H.264/HEVC + audio AAC/MP3',
    'mkv·avi·mov·ts 등':
        'mkv, avi, mov, ts, etc.',
    'mp4에서 다른 음성 트랙을 고를 때':
        'Un mp4 al elegir otra pista de audio',
    '10비트 H.264':
        'H.264 de 10 bits',
    'XviD 등 TV가 못 읽는 영상':
        'XviD y otros vídeos que la TV no puede leer',
    '도움말':
        'Ayuda',
    '단축키':
        'Atajos de teclado',
    '5초 뒤로 / 앞으로':
        'Atrás / adelante 5 s',
    '영상':
        'Vídeo',
    'PC 자원 사용':
        'Usa recursos del PC',
    '화질 조금 낮아짐':
        'Calidad de imagen algo menor',
    '닫기':
        'Cerrar',
    '그대로 보냄':
        'Enviado directamente',
    'HLS 변환':
        'HLS',
    'HLS 재인코딩':
        'HLS recodificado',
    '{app} 정보':
        'Acerca de {app}',
    'IP로 기기 추가':
        'Añadir dispositivo por IP',
    '크롬캐스트 IP 주소:':
        'Dirección IP del Chromecast:',
    '확인 실패':
        'no se pudo comprobar',
    '인코더: {name}':
        'Codificador: {name}',
    '올바른 IP 주소가 아닙니다: {ip}':
        'No es una dirección IP válida: {ip}',
    '로컬 동영상 → Chromecast 송출':
        'Vídeos locales → Chromecast',
    '감지 중 또는 없음':
        'detectando o ninguno',
    '미연결':
        'Sin conexión',
    '연결 중':
        'Conectando',
    '연결됨':
        'Conectado',
    '끊김':
        'Desconectado',
    '파일':
        'Archivo',
    '영상 그대로':
        'vídeo sin cambios',
    '자막 싱크 {sign} 0.5초 (Shift+클릭: 0.1초)':
        'Sincronía de subtítulos {sign}0,5 s (Mayús+clic: 0,1 s)',
    '{ext} 그대로 보냄':
        '{ext} enviado directamente',
    '{ext} → HLS 변환':
        '{ext} → HLS',
    '{ext} → HLS 재인코딩':
        '{ext} → HLS recodificado',
    '음성 그대로':
        'audio sin cambios',
    '음성 AAC 2ch로 변환':
        'audio convertido a AAC estéreo',
    '기기 다시 찾기 (F5)':
        'Buscar dispositivos de nuevo (F5)',
    '{n}초 뒤로':
        'Atrás {n} s',
    '재생 / 일시정지 (Space)':
        'Reproducir / Pausa (Espacio)',
    '{n}초 앞으로':
        'Adelante {n} s',
    '정지 (S) · TV 플레이어 종료':
        'Detener (S) · cierra el reproductor del televisor',
    '음소거 (M)':
        'Silencio (M)',
    '자막 작게':
        'Subtítulos más pequeños',
    '자막 크게':
        'Subtítulos más grandes',
    '끄기':
        'Desactivados',
    '{n}초':
        '{n} s',
    '{name}을(를) mDNS로 찾지 못해 {host}로 확인합니다…':
        'No se encontró {name} con mDNS. Comprobando {host}…',
    '기기를 찾는 중…':
        'Buscando dispositivos…',
    '{ip} 확인 중… 목록에 나타나면 [연결]을 누르세요.':
        'Comprobando {ip}… Pulse [Conectar] cuando aparezca en la lista.',
    ' — 다시 연결 중…':
        ' — reconectando…',
    ' — {n}초 동안 다시 찾는 중…':
        ' — buscando de nuevo durante {n} s…',
    '동영상 열기':
        'Abrir vídeo',
    '재생 완료':
        'Reproducción terminada',
    '캐시를 비웠습니다.':
        'Se vació la caché.',
    '종료 중… (정지 → TV 플레이어 종료 → 연결 해제)':
        'Saliendo… (detener → cerrar el reproductor del televisor → desconectar)',
    '음성':
        'Audio',
    '자막':
        'Subtítulos',
    '자막 크기':
        'Tamaño de subtítulos',
    '자막 싱크':
        'Sincronía de subtítulos',
    '동영상 파일을 여기에 끌어다 놓으세요':
        'Arrastre aquí un archivo de vídeo',
    '먼저 기기를 연결하세요':
        'Conecte primero un dispositivo',
    '연결 해제':
        'Desconectar',
    '연결':
        'Conectar',
    '{name}을(를) 찾지 못했습니다.':
        'No se encontró {name}.',
    '기기를 먼저 찾으세요 (F5).':
        'Busque primero los dispositivos (F5).',
    '다시 연결됨. 끊긴 위치부터 이어 갑니다.':
        'Reconectado. Continuando desde donde se detuvo.',
    '기기에 다시 연결하지 못했습니다. [연결]을 눌러 주세요.':
        'No se pudo volver a conectar al dispositivo. Pulse [Conectar].',
    '파일이 없습니다: {path}':
        'No se encontró el archivo: {path}',
    '재생 요청을 보냈습니다.':
        'Solicitud de reproducción enviada.',
    '불러오기 실패: {msg}':
        'Error al cargar: {msg}',
    '음성 변경 실패: {msg}':
        'Error al cambiar la pista de audio: {msg}',
    'TV에서 플레이어가 종료됨':
        'Se cerró el reproductor en el televisor',
    '불러오기 실패: {name} ({code})':
        'Error al cargar: {name} ({code})',
    '연결됨. 재생 버튼을 누르면 이어서 재생합니다.':
        'Conectado. Pulse Reproducir para continuar.',
    '동영상':
        'Vídeos',
    '모든 파일':
        'Todos los archivos',
    '먼저 기기를 연결하세요.':
        'Conecte primero un dispositivo.',
    '지금 재생 중인 파일을 멈추고 새 파일로 바꾸겠습니까?\n\n{name}':
        '¿Detener el archivo en reproducción y cambiar al nuevo?\n\n{name}',
    '음성 트랙을 바꿨습니다.':
        'Pista de audio cambiada.',
    '로그 기록 켬':
        'Registro activado',
    '로그 기록 끔':
        'Registro desactivado',
    '자막 추출 캐시를 지우겠습니까?\n(다음에 열 때 다시 만듭니다)':
        '¿Vaciar la caché de subtítulos?\n(Se vuelve a crear la próxima vez que se abra un archivo)',
    '파일을 불러오는 중입니다. 종료하겠습니까?':
        'Se está cargando un archivo. ¿Salir de todos modos?',
    '마지막 기기':
        'El último dispositivo',
    '메뉴':
        'Menú',
    '파일 열기…':
        'Abrir archivo…',
    'IP로 기기 추가…':
        'Añadir dispositivo por IP…',
    '기기 연결 해제':
        'Desconectar dispositivo',
    '옵션':
        'Opciones',
    '시작 시 마지막 기기 자동 연결':
        'Conectar al último dispositivo al iniciar',
    '테마':
        'Tema',
    '언어':
        'Idioma',
    '로그 기록':
        'Registro',
    '로그 폴더 열기':
        'Abrir carpeta de registros',
    '캐시 비우기…':
        'Vaciar caché…',
    '정보':
        'Ayuda',
    'CastPlayer 정보':
        'Acerca de CastPlayer',
    '시스템 설정 따르기':
        'Usar la configuración del sistema',
    '어둡게':
        'Oscuro',
    '밝게':
        'Claro',
    # ---- ui/tracks.py (F9-11, D096) ----
    '한국어': 'Coreano',
    '영어': 'Inglés',
    '일본어': 'Japonés',
    '중국어': 'Chino',
    '스페인어': 'Español',
    '프랑스어': 'Francés',
    '독일어': 'Alemán',
    '러시아어': 'Ruso',
    '이탈리아어': 'Italiano',
    '포르투갈어': 'Portugués',
    '태국어': 'Tailandés',
    '베트남어': 'Vietnamita',
    '인도네시아어': 'Indonesio',
    '아랍어': 'Árabe',
    '힌디어': 'Hindi',
    '언어 정보 없음': 'Sin información de idioma',
    '기본': 'predeterminada',
    '내장 {fmt}': 'integrado {fmt}',
    '{n}줄': '{n} líneas',
    # ---- 불러오기 취소 (F2-10, D099) ----
    '취소': 'Cancelar',
    '불러오기를 취소했습니다.': 'Se canceló la carga.',
    '정보 읽기': 'Leyendo información del archivo',
    '음성 변경을 취소했습니다.': 'Se canceló el cambio de audio.',
    '추출 중': 'Extrayendo',
    '추출 중단': 'Extracción detenida',
    '추출 중 {n}%': 'Extrayendo {n}%',
    '내장 자막을 준비했습니다.': 'Los subtítulos incrustados están listos.',
    '불러오는 중': 'Cargando',
    '다시 연결 중': 'Reconectando',
    '정지': 'Detenido',
    '재생 중': 'Reproduciendo',
    '버퍼링 중': 'Almacenando en búfer',
    '자막 추출 {n}%': 'Extrayendo subtítulos {n}%',
    '기기를 찾았습니다: {name}': 'Dispositivo encontrado: {name}',
    '기기 찾기 완료: {n}대': 'Búsqueda terminada: {n} dispositivos',
    '기기를 찾지 못했습니다. 같은 네트워크인지 확인하거나 메뉴 → IP로 기기 추가를 쓰세요.': 'No se encontraron dispositivos. Comprueba que estás en la misma red o usa Menú → Añadir dispositivo por IP….',
    '기기 찾는 중 · {n}대': 'Buscando dispositivos · {n}',
    '로그': 'Registro',
    '로그(자세히)': 'Registro (detallado)',
    '내장 자막을 붙이려고 다시 불러옵니다.': 'Recargando para añadir los subtítulos incrustados.',
    '자막 싱크를 반영하려고 다시 불러옵니다.': 'Recargando para aplicar la sincronía de subtítulos.',
}

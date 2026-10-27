"""크롬캐스트에 알려줄 PC 측 IP 결정."""
import socket


def local_ip_for(target_host: str) -> str:
    """target_host로 가는 경로에 사용되는 로컬 IP.

    UDP connect는 실제 패킷을 보내지 않고 라우팅 경로만 정한다.
    유선/무선/가상 어댑터(Hyper-V, VPN 등)가 섞여 있어도
    크롬캐스트와 통신 가능한 인터페이스의 IP가 선택된다.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((target_host, 9))
        return s.getsockname()[0]

import socket

def check_port(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect((host, port))
        print(f"Port {port} on {host} is OPEN")
        s.close()
        return True
    except Exception as e:
        print(f"Port {port} on {host} is CLOSED: {e}")
        return False

if __name__ == "__main__":
    check_port("127.0.0.1", 5432)

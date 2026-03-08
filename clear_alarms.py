from hv.backend.caen import CAENBackend

def main():

    print("Conectando al módulo HV...")

    backend = CAENBackend()
    backend.connect()

    n_channels = backend.get_channel_count()

    print(f"Limpiando alarmas en {n_channels} canales")

    for ch in range(n_channels):
        try:
            backend.clear_channel_alarms(ch)
            print(f"CH{ch}: alarms cleared")
        except Exception as e:
            print(f"CH{ch}: error -> {e}")

    print("Done.")

if __name__ == "__main__":
    main()

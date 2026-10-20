import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

def main():
    # Cria a instância da aplicação Qt
    app = QApplication(sys.argv)

    # Instancia e exibe a nossa janela principal
    window = MainWindow()
    window.show()

    # Inicia o loop de eventos da interface gráfica
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
import flet as ft

def main(page: ft.Page):
    chat = ft.Column()
    new_message = ft.TextField()

    # Envia a mensagem quando o botão send é carregado
    def send_click(e):
        chat.controls.append(ft.Text(new_message.value))
        new_message.value = ""

    # Adiciona a caixa de chat e o campo de texto para a nova mensagem
    page.add(
        chat,
        ft.Row(controls=[new_message, ft.Button("Send", on_click=send_click)]),
    )


ft.run(main)
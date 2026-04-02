from dataclasses import dataclass
import flet as ft

@dataclass
class Message:
    user: str
    text: str
    message_type: str
    
def main(page: ft.Page):
    chat = ft.Column()
    new_message = ft.TextField()

    def on_message(message: Message):
        if message.message_type == "chat_message":
            chat.controls.append(ft.Text(f"{message.user}: {message.text}"))
        elif message.message_type == "login_message":
            chat.controls.append(
                ft.Text(message.text, italic==True, color=ft.Colors.Black_45, size=12)
            )
        page.update()
        
    page.pubsub.subscribe(on_message)

    # Envia a mensagem quando o botão send é carregado
    def send_click(e):
        page.pubsub.send_all(
            Message(
                user=page.session.store.get("user_name"), 
                text=new_message.value, 
                message_type="chat_message",
            )
        )
        new_message.value = ""
    
    user_name = ft.TextField(label="Introduza o seu nome")
    
    def join_click(e):
        if not user_name.value:
            user_name.error = "O nome não pode estar em branco"
            user_name.update()
        else:
            page.session.store.set("user_name", user_name.value)
            page.pop_dialog()
            page.pubsub.send_all(
                Message(
                    user=user_name.value, 
                    text=f"{user_name.value} has joined the chat!", 
                    message_type="login_message"
                    )
                )
    
    page.show_dialog(
        ft.AlertDialog(
            open=True,
            modal=True,
            title=ft.Text("Bem vindo ao LESTI!"),
            content=ft.Column([user_name], tight=True),
            actions=[ft.Button(content="Join Chat", on_click=join_click)],
            actions_alignment=ft.MainAxisAlignment.END,
        )
    )

    page.add(chat, ft.Row(controls=[new_message, ft.Button("Send", on_click=send_click)]))

ft.run(main)
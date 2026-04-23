from __future__ import annotations

from django.core.files.storage import FileSystemStorage


class PrivateMediaStorage(FileSystemStorage):
    """
    Storage local privado.
    Os arquivos só devem ser entregues por views autenticadas.
    """

    def url(self, name):
        raise ValueError("Arquivos privados nao possuem URL publica.")

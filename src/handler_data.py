import hashlib
import os
import tempfile
from collections import defaultdict
from json import dump, load
from threading import RLock
from src.config import settings

_LOCKS_GUARD = RLock()
_LOCKS_BY_USER = defaultdict(RLock)


class Data:
    def __init__(self, id):
        self.id = str(id)
        self.storage_id = self._sanitize_id(self.id)
        self.DATA_DIR = settings.DATA_DIR
        self.user_dossier = os.path.join(self.DATA_DIR, self.storage_id)
        self.fichier = [
            'historique.json',
            'instructions.json',
            'function_tools.json',
            'vector.json',
            'files.json',
            'uploaded_files.json',
            'containers.json',
        ]
        self.set_all_path_files()
        self.init_directory()

    @staticmethod
    def _sanitize_id(raw_id: str) -> str:
        candidate = raw_id.strip()
        if candidate and all(c.isalnum() or c in "._-" for c in candidate):
            return candidate[:120]
        return "id_" + hashlib.sha256(raw_id.encode("utf-8")).hexdigest()

    def _get_lock(self):
        with _LOCKS_GUARD:
            return _LOCKS_BY_USER[self.user_dossier]

    def read_file(self, filepath):
        with self._get_lock():
            with open(filepath, "r", encoding="utf-8") as file:
                return load(file)
    def append_file(self, filepath, donnee):
        with self._get_lock():
            with open(filepath, "a", encoding="utf-8") as file:
                dump(donnee, file, indent=2, ensure_ascii=False)
    def write_file(self, filepath, donnee):
        with self._get_lock():
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with tempfile.NamedTemporaryFile("w", delete=False, dir=os.path.dirname(filepath), encoding="utf-8") as file:
                dump(donnee, file, indent=2, ensure_ascii=False)
                temp_name = file.name
            os.replace(temp_name, filepath)

    def set_all_path_files(self):
        tab = []
        for file in self.fichier:
            tab.append(os.path.join(self.user_dossier , file))
        self.fichier = tab
    def init_directory(self):
        with self._get_lock():
            os.makedirs(self.DATA_DIR, exist_ok=True)
            os.makedirs(self.user_dossier, exist_ok=True)
            for pathfile in self.fichier:
                if not os.path.exists(pathfile):
                    with open(pathfile, 'w', encoding="utf-8") as f:
                        if (
                            "historique" in pathfile
                            or 'vector' in pathfile
                            or "files" in pathfile
                            or "containers" in pathfile
                        ):
                            dump([], f)
                        else:
                            dump({}, f)

    def add_instructions(self, new_instructions):
        if new_instructions == "": return
        instruction_path = os.path.join(self.user_dossier , "instructions.json")
        instructions = self.read_file(instruction_path)
        try: instructions["instructions"] += "\n"+new_instructions
        except KeyError: instructions["instructions"] = new_instructions
        self.write_file(instruction_path, instructions)
    def remove_instructions(self):
        instruction_path = os.path.join(self.user_dossier , "instructions.json")
        self.write_file(instruction_path, {})
    def change_instructions(self, new_instructions):
        instruction_path = os.path.join(self.user_dossier , "instructions.json")
        self.write_file(instruction_path, {"instructions":str(new_instructions)})

    def get_line(self, role, content):
        return {"role":str(role), "content":content}
    def add_historique(self, role, new_historique):
        if role not in ["user", "assistant", "system", "developer"]: return
        if new_historique == "": return
        new_historique = self.get_line(role, new_historique)
        historique_path = os.path.join(self.user_dossier , "historique.json")
        historique = self.read_file(historique_path)
        historique.append(new_historique)
        self.write_file(historique_path, historique)
    def remove_historique(self):
        historique_path = os.path.join(self.user_dossier , "historique.json")
        self.write_file(historique_path, [])
    def remove_last_echange(self):
        historique_path = os.path.join(self.user_dossier , "historique.json")
        try:
            historique = self.get_historique()[:-2]
            self.write_file(historique_path, historique)
        except: pass
    def change_historique(self, new_historique):
        historique_path = os.path.join(self.user_dossier , "historique.json")
        self.write_file(historique_path, new_historique)

    def add_historique_image(self, content):
        image_path = os.path.join(self.user_dossier, "image_historique.png")
        with self._get_lock():
            with open(image_path, "wb") as file:
                file.write(content)
    def remove_historique_image(self):
        image_path = os.path.join(self.user_dossier, "image_historique.png")
        with self._get_lock():
            if os.path.exists(image_path):
                os.remove(image_path)
    def get_historique_image(self):
        image_path = os.path.join(self.user_dossier, "image_historique.png")
        with self._get_lock():
            if os.path.exists(image_path):
                return open(image_path, "rb")
            else: return False


    def get_function_tools(self):
        return self.read_file(self.user_dossier + "/function_tools.json")
    def get_historique(self):
        return self.read_file(self.user_dossier+"/historique.json")
    def get_instructions(self):
        return self.read_file(self.user_dossier+"/instructions.json")
    def get_vector(self):
        return self.read_file(self.user_dossier+"/vector.json")
    def get_files(self):
        return self.read_file(self.user_dossier+"/files.json")
    def get_uploaded_files(self):
        return self.read_file(self.user_dossier+"/uploaded_files.json")
    def get_containers(self):
        return self.read_file(self.user_dossier+"/containers.json")

    def add_vector(self, vs_id):
        vs_path = os.path.join(self.user_dossier , "vector.json")
        liste_vectors = self.get_vector()
        liste_vectors.append(vs_id)
        self.write_file(vs_path, liste_vectors)

    def add_files(self, file_id):
        file_path = os.path.join(self.user_dossier, "files.json")
        liste_files = self.get_files()
        liste_files.append(file_id)
        self.write_file(file_path, liste_files)

    def replace_files(self, file_ids):
        file_path = os.path.join(self.user_dossier, "files.json")
        self.write_file(file_path, list(file_ids))

    def add_uploaded_file(self, file_id):
        uploaded_files_path = os.path.join(self.user_dossier, "uploaded_files.json")
        uploaded_files = self.get_uploaded_files()
        uploaded_files.append(file_id)
        self.write_file(uploaded_files_path, uploaded_files)

    def replace_uploaded_files(self, file_ids):
        uploaded_files_path = os.path.join(self.user_dossier, "uploaded_files.json")
        self.write_file(uploaded_files_path, list(file_ids))

    def add_container(self, container_id):
        container_path = os.path.join(self.user_dossier, "containers.json")
        containers = self.get_containers()
        containers.append(container_id)
        self.write_file(container_path, containers)

    def replace_containers(self, container_ids):
        container_path = os.path.join(self.user_dossier, "containers.json")
        self.write_file(container_path, list(container_ids))

    def clear(self):
        import shutil
        with self._get_lock():
            if os.path.isdir(self.user_dossier):
                shutil.rmtree(self.user_dossier)



if __name__ == '__main__':
    data = Data("billy")
    data.change_historique("user", "dsfezfz")

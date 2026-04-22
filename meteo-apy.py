from os import environ, chdir, makedirs
from urllib.request import urlopen
import json
from os.path import dirname, abspath, isfile, getmtime
from time import time

chdir(dirname(abspath(__file__)))

def load_env(path=".env"):
    if isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in map(str.strip, f.readlines()):
                if len(line) < 3 or line[0] == "#" or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                environ[key] = value


def _to_num(s: str):
    try:
        f = float(s)
    except ValueError:
        return s
    i = int(f)
    if i == f:
        return i
    return f


def _parse(obj, key: str = None):
    if obj is None:
        return None
    if isinstance(obj, list):
        new_obj = []
        for i in obj:
            i = _parse(i, key=key)
            if i is not None:
                new_obj.append(i)
        if len(new_obj) == 0:
            return None
        if key in ("velocidad", "direccion"):
            if len(new_obj) != 1:
                raise ValueError(obj)
            return new_obj[0]
        return new_obj
    if isinstance(obj, dict):
        new_obj = {}
        for k, v in obj.items():
            v = _parse(v, key=k)
            if v is not None:
                new_obj[k] = v
        if tuple(sorted(new_obj.keys())) in ((), ("periodo",), ("hora", )):
            return None
        if key == "estadoCielo":
            new_obj['value'] = new_obj['descripcion']
            del new_obj['descripcion']
        return new_obj
    if isinstance(obj, str):
        obj = obj.strip()
        if len(obj) == 0:
            return None
        return _to_num(obj)
    return obj


def _get_json(url: str):
    with urlopen(url) as r:
        b = r.read()
        t = b.decode("latin-1")
        return json.loads(t)


def _provicina(nombre: str, provincia: str):
    if (nombre, provincia) == (None, None):
        return None
    if None in (nombre, provincia):
        return provincia or nombre
    if nombre == provincia:
        return provincia
    if nombre in provincia:
        return provincia
    if provincia in nombre:
        return nombre
    return f"{provincia}, {nombre}"


class Meteo:
    def __init__(self, id: str, minutes_cache: int = 30):
        self.__root = "https://opendata.aemet.es/opendata/api"
        self.__api_key = environ['AEMET_KEY']
        self.__seconds_cache =  minutes_cache * 60
        self.__id = id

    def __get_json(self, url: str):
        r = _get_json(url)
        d = _get_json(r['datos'])
        return d

    def __get_data(self, path: str) -> dict:
        file = f".{path}{self.__id}.json"
        if isfile(file) and (time() - getmtime(file)) <= self.__seconds_cache:
            with open(file, "r") as f:
                return json.load(f)

        url = f"{self.__root}{path}{self.__id}?api_key={self.__api_key}"
        data = self.__get_json(url)
        data = _parse(data)
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise ValueError(data)
        data = data[0]

        data = {
            "id": data['id'],
            "elaborado": data['elaborado'].replace("T", " ")[:16],
            "provincia": _provicina(data['nombre'], data['provincia']),
            **data['prediccion']
        }

        makedirs(dirname(file), exist_ok=True)
        with open(file, "w") as f:
            json.dump(data, f, indent=2)
        return data
    
    def get_horaria(self):
        return self.__get_data('/prediccion/especifica/municipio/horaria/')

    def get_diaria(self):
        return self.__get_data('/prediccion/especifica/municipio/diaria/')

if __name__ == "__main__":
    load_env()
    m = Meteo(28079)
    d = m.get_diaria()
    d = m.get_horaria()
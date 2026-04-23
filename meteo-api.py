from os import environ, chdir, makedirs
from urllib.request import urlopen
from urllib.error import HTTPError
import json
from os.path import dirname, abspath, isfile, getmtime
from time import time
import re
from typing import NamedTuple
from time import sleep


chdir(dirname(abspath(__file__)))


class MinMax(NamedTuple):
    min: float
    max: float


class Data(NamedTuple):
    fecha: str
    periodo: MinMax
    # Diaria/Horaria: Descripción del estado del cielo
    estadoCielo: str
    # Horaria: Milímetros (mm) de precipitación durante la hora anterior
    precipitacion: float
    # Diaria/Horaria: % de probabilidad de precipitación
    probPrecipitacion: int
    # Horaria: % de probabilidad de tormenta
    probTormenta: int
    # Horaria: milímetros (mm) de nieve que se prevé que caiga durante la hora anterior
    nieve: float
    # Horaria: % de probabilidad de precipitación de nieve
    probNieve: int
    # Horaria: Grados celsius
    # Diaria: [Min-Max] Grados celsius
    temperatura: MinMax
    # Horaria: Grados celsius
    # Diaria: [Min-Max] Grados celsius
    sensTermica: MinMax
    # Horaria: % de humedad relativa
    # Diaria: [Min-Max] % de humedad relativa
    humedadRelativa: MinMax
    # Diaria/Horaria: km/h viento
    viento: int
    # Diaria/Horaria: km/h racha máxima
    rachaMax: int
    # Diaria: Índice ultravioleta máximo
    uvMax: int


def load_env(path=".env"):
    if isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in map(str.strip, f.readlines()):
                line = re.sub(r"^\s*export\s+", "", line)
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
        if key in ("elaborado", "fecha"):
            return obj.replace("T", " ")[:16 if key == "elaborado" else 10]
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
        self.__root = "https://opendata.aemet.es/opendata/api/prediccion/especifica/municipio"
        self.__api_key = tuple(sorted(set(environ['AEMET_KEY'].strip().split())))
        self.__seconds_cache = minutes_cache * 60
        self.__id = id

    def __get_json(self, path: str):
        prefix = f"{self.__root}{path}/{self.__id}"
        for api_key in self.__api_key:
            max_tries = 3
            for i in range(0, max_tries + 1):
                try:
                    url = f"{prefix}?api_key={api_key}"
                    r = _get_json(url)
                    d = _get_json(r['datos'])
                    return d
                except HTTPError as e:
                    if i==max_tries or not re.search("Too Many Requests", str(e), flags=re.I):
                        raise
                sleep(2*(i+1))

    def __get_data(self, path: str) -> dict:
        file = f"cache/{self.__id}/{path}.json"
        if isfile(file) and (time() - getmtime(file)) <= self.__seconds_cache:
            with open(file, "r") as f:
                return json.load(f)

        data = self.__get_json(path)
        new_data = self.__parse_data(data)
        if new_data is None:
            raise ValueError(data)

        makedirs(dirname(file), exist_ok=True)
        with open(file, "w") as f:
            json.dump(new_data, f, indent=2)
        return data

    def __parse_data(self, data: dict):
        data = _parse(data)
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            return None
        data = data[0]
        dia = data['prediccion']['dia']
        if not isinstance(dia, list) or len(dia) == 0:
            return None
        dias: dict[str, dict] = {}
        for d in dia:
            if not isinstance(d, dict):
                return None
            fecha = d.pop('fecha', None)
            if fecha in dias:
                return None
            vr = d.pop('vientoAndRachaMax', None)
            if vr:
                if not isinstance(vr, list):
                    return None
                if set(d.keys()).intersection({"viento", "rachaMax"}):
                    return None
                d['viento'] = [x for x in vr if "direccion" in x]
                d['rachaMax'] = [x for x in vr if "value" in x]
            vi = d.pop('viento', None)
            if vi:
                if not isinstance(vi, list):
                    return None
                for v in vi:
                    if not isinstance(v, dict) or "velocidad" not in v or "value" in v:
                        return None
                    v['value'] = v.pop('velocidad')
                d['viento'] = vi
            dias[fecha] = d

        data = {
            "id": data['id'],
            "elaborado": data['elaborado'],
            "provincia": _provicina(data['nombre'], data['provincia']),
            'prediccion': dias
        }

        return data

    def get_horaria(self):
        return self.__get_data('/horaria')
        template = Data(**{k: None for k in Data._fields})
        datos: dict[tuple[str, MinMax], Data] = {}

        def _add(fecha: str, periodo: MinMax, **kwargs):
            k = (fecha, periodo)
            i = datos.get(k, template._replace(fecha=fecha, periodo=periodo))
            i = i._replace(**kwargs)
            datos[k] = i

        for d in data['dia']:
            f = d['fecha']
            for k, v in d.items():
                if not isinstance(v, list):
                    continue
                for i in v:
                    p = MinMax(i['periodo'], i['periodo']+1)
                    key = k
                    val = None
                    if k == "vientoAndRachaMax":
                        if "velocidad" in i:
                            val = i['velocidad']
                            key = "viento"
                        else:
                            val = i['value']
                            key = "rachaMax"
                    else:
                        val = i['value']
                    if val is None:
                        raise ValueError(f"{k} -> {v}")
                    if k in ("temperatura", "sensTermica", "humedadRelativa"):
                        v = MinMax(v, v)
                    _add(f, p, **{key: val})
        return tuple(datos.values())

    def get_diaria(self):
        return self.__get_data('/diaria')
    
    def get_prediccion(self):
        horaria = self.get_horaria()
        diaria = self.get_diaria()


if __name__ == "__main__":
    load_env()
    m = Meteo(28079)
    d = m.get_prediccion()
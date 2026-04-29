from os import environ, chdir, makedirs
from urllib.request import urlopen
from urllib.error import HTTPError
import json
from os.path import dirname, abspath, isfile, getmtime
from time import time
import re
from typing import NamedTuple
from time import sleep
from types import MappingProxyType
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict


def gNow():
    z = ZoneInfo("Europe/Madrid")
    return datetime.now(z)


chdir(dirname(abspath(__file__)))
re_sp = re.compile(r"\s+")

class MinMax(NamedTuple):
    min: float
    max: float


class Data(NamedTuple):
    # Diaria/Horaria: Descripción del estado del cielo
    estadoCielo: str
    # Horaria: Milímetros (mm) de precipitación durante la hora anterior
    # precipitacion: float
    # Diaria/Horaria: % de probabilidad de precipitación
    probPrecipitacion: int
    # Horaria: % de probabilidad de tormenta
    probTormenta: int
    # Horaria: % de probabilidad de precipitación de nieve
    probNieve: int
    # Horaria: milímetros (mm) de nieve que se prevé que caiga durante la hora anterior
    # nieve: float
    # Diaria: metros (m) de nieve
    # cotaNieveProv: float
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
    # rachaMax: int
    # Diaria: Índice ultravioleta máximo
    # uvMax: int

    @classmethod
    def template(cls):
        return cls(**{k: None for k in cls._fields})


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
        if key in ("elaborado", "fecha", "periodo"):
            obj = re_sp.sub("", obj)
        if len(obj) == 0:
            return None
        if key in ("elaborado", "fecha"):
            return obj.replace("T", " ")[:16 if key == "elaborado" else 10]
        if key == "periodo":
            if len(obj) == 4:
                return obj[:2]+'-'+obj[2:]
            if len(obj) == 2:
                v = int(obj)
                return f"{v:02d}-{v+1:02d}"
            if not re.match(r"^\d{2}-\d{2}$", obj):
                raise ValueError(obj)
            return obj
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
        return new_data

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
        data = self.__get_data('/horaria')
        template = Data.template()
        datos: dict[str, Data] = {}

        def _add(k: str, **kwargs):
            i = datos.get(k, template)
            i = i._replace(**kwargs)
            datos[k] = i

        for fc, d in data['prediccion'].items():
            for key, v in d.items():
                if key not in Data._fields:
                    continue
                for i in v:
                    val = i['value']
                    pr = i['periodo']
                    if val is None:
                        raise ValueError(f"{k} -> {v}")
                    #if key in ("precipitacion", "nieve"):
                    #    a, b = map(int, pr.split("-"))
                    #    pr = f"{a-1:02d}-{b-1:02d}"
                    if key in ("temperatura", "sensTermica", "humedadRelativa"):
                        val = MinMax(val, val)
                    _add(f"{fc} {pr}", **{key: val})
        return MappingProxyType(dict(sorted(datos.items())))

    def get_diaria(self):
        data = self.__get_data('/diaria')
        template = Data.template()
        datos: dict[str, Data] = {}

        def _add(k: str, **kwargs):
            i = datos.get(k, template)
            i = i._replace(**kwargs)
            datos[k] = i

        for fc, d in data['prediccion'].items():
            for key, v in d.items():
                if key not in Data._fields:
                    continue
                if isinstance(v, dict):
                    v = [v]
                for i in v:
                    p = i.get("periodo", "00-24")
                    val = None
                    is_minmax = ("temperatura", "sensTermica", "humedadRelativa")
                    if key in is_minmax:
                        val = MinMax(i["minima"], i["maxima"])
                    else:
                        val = i['value']
                    if val is None:
                        raise ValueError(f"{key} -> {v}")
                    _add(f"{fc} {p}", **{key: val})
                    for x in i.get("dato", tuple()):
                        h = x['hora']
                        val = x['value']
                        if key in is_minmax:
                            val = MinMax(val, val)
                        if val is None:
                            raise ValueError(f"{key} -> {v}")
                        _add(f"{fc} {h:02d}-{h+1:02d}", **{key: val})
        return MappingProxyType(dict(sorted(datos.items())))
    
    def get_prediccion(self):
        datos: dict[str, Data] = {}
        horaria = self.get_horaria()
        diaria = self.get_diaria()
        for k in sorted(set(horaria.keys()).union(diaria.keys())):
            datos[k] = self.__merge(
                k,
                horaria.get(k),
                diaria.get(k)
            )
        return MappingProxyType(datos)
    
    def __merge(self, p: str, h: Data, d: Data):
        if (h, d) == (None, None):
            raise ValueError()
        if None in (h, d):
            return h or d
        a, b = map(int, p.split()[-1].split("-"))
        _h = h._asdict()
        _d = d._asdict()
        obj = {}
        for k in sorted(set(_h.keys()).union(_d.keys())):
            vh = _h.get(k)
            vd = _d.get(k)
            if None in (vh, vd):
                obj[k] = vd or vh
                continue
            if vh == vd:
                obj[k] = vd
                continue
            if b == a+1:
                obj[k] = vh
                continue
            raise ValueError(f"{p} {k} {vh} {vd}")
        return Data(**obj)
    
    def get_day(self, fch: str):
        data = {k: v for k, v in self.get_prediccion().items() if k.startswith(f"{fch} ")}

        data_hour: dict[int, dict[str, MinMax]] = defaultdict(dict)
        for k, v in data.items():
            _, p = k.split()
            x1, x2 = map(int, p.split("-"))
            for k, mm in v._asdict().items():
                if not isinstance(mm, MinMax):
                    continue
                for i in range(x1, x2+1):
                    obj = data_hour.get(i, dict())
                    old = obj.get(k)
                    if old is None:
                        obj[k] = mm
                    else:
                        obj[k] = MinMax(min(old.min, mm.min), max(old.max, mm.max))
                    data_hour[i] = obj

        def _get(f: str, a: int, b: int):
            val: MinMax | None = None
            for h in range(a, b+1):
                v = data_hour.get(h, dict()).get(f)
                if v is None:
                    continue
                if val is None:
                    val = v
                else:
                    val = MinMax(min(val.min, v.min), max(val.max, v.max))
            return val
        
        r: dict[str, Data] = dict()
        for f, v in data.items():
            _, k = f.split()
            a, b = map(int, k.split("-"))
            if v.temperatura is None:
                v = v._replace(temperatura=_get('temperatura', a, b))
            if v.sensTermica is None:
                v = v._replace(sensTermica=_get('sensTermica', a, b))
            if v.humedadRelativa is None:
                v = v._replace(humedadRelativa=_get('humedadRelativa', a, b))
            r[k] = v

        return r

    def get_period(self, fch: str):
        f, p = fch.split()
        if p in ("00-12", "12-24", "00-24"):
            return self.get_day(f)[p]
        return self.get_prediccion()[fch]

    def get(self):
        now = gNow()
        today = now.strftime("%Y-%m-%d")
        tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        dates = []
        dates.append(f"{today} {now.hour:02d}-{now.hour+1:02d}")
        if now.hour <= 20:
            dates.append(f"{today} 20-21")
        if now.hour <= 10:
            dates.append(f"{today} 00-12")
            dates.append(f"{today} 12-24")
        elif now.hour >= 21:
            dates.append(f"{tomorrow} 00-12")
            dates.append(f"{tomorrow} 12-42")
        else:
            dates.append(f"{today} 12-24")
            dates.append(f"{tomorrow} 00-24")
        r: dict[str, Data] = {}
        for d in dates:
            r[d] = self.get_period(d)
        return MappingProxyType(r)


if __name__ == "__main__":
    load_env()
    m = Meteo(28079)
    d = m.get()
    print(*d.items(), sep="\n")
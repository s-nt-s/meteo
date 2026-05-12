
from urllib.request import urlopen
import xml.etree.ElementTree as ET
from typing import NamedTuple, Optional, Union
from functools import cached_property
import re
import json
from pathlib import Path
from types import MappingProxyType
from datetime import datetime, timedelta, date
import logging
import argparse
from collections import defaultdict

logger = logging.getLogger(__name__)

re_sp = re.compile(r'\s+')
ROOT_DIR = Path(__file__).absolute().parent
WD = ('L', 'M', 'X', 'J', 'V')


def _h1(x: str, w: int):
    pd = w - len(x) - 2
    chars = '=' * int(pd/2)
    if pd % 2 == 0:
        return f'{chars} {x} {chars}'
    return f'{chars} {x} {chars}='


def _parse_obj(obj):
    if getattr(obj, "_asdict", None) is not None:
        obj = obj._asdict()
    if isinstance(obj, MappingProxyType):
        obj = dict(obj)
    if isinstance(obj, (list, tuple, set)):
        obj = list(map(lambda x: _parse_obj(x), obj))
    if isinstance(obj, dict):
        obj = {k: _parse_obj(v) for k, v in obj.items()}
    if isinstance(obj, dict):
        obj = {k: v for k, v in obj.items()}
    if isinstance(obj, str):
        obj = obj.strip()
    if isinstance(obj, list):
        obj = [a for a in obj if a is not None]
    if isinstance(obj, dict):
        obj = {k: v for k, v in obj.items() if v is not None}
    if isinstance(obj, (list, dict, str)) and len(obj) == 0:
        return None
    return obj


def _trim(s: str | ET.Element | None) -> str:
    if isinstance(s, ET.Element):
        s = s.text
    if s is None:
        return None
    s = re_sp.sub(" ", s).strip()
    if len(s) == 0:
        return None
    return s


def _val(n: ET.Element):
    if n.tag == "estado_cielo":
        return _trim(n.get("descripcion"))
    if n.tag == "viento":
        v = _trim(n.find("velocidad"))
        return None if v is None else int(v)
    v = _trim(n)
    if v is None:
        return None
    return int(v)


def _or(a, b):
    if a is not None:
        return a
    return b


OK_PERIODO = (
    "00-06",
    "00-12",
    "00-24",
    "06-12",
    "12-18",
    "12-24",
    "18-24",
)
OK_HORA = (
    "06",
    "12",
    "18",
    "24",
)
OK_CAMPO = (
    "prob_precipitacion",
    "cota_nieve_prov",
    "estado_cielo",
    "racha_max",
    "uv_max",
    "viento",
    "temperatura",
    "sens_termica",
    "humedad_relativa",
)


def xml_to_json(tree: ET.Element):
    OK_P = OK_PERIODO + OK_HORA
    pre = {}
    obj = {
        "id": int(tree.get("id")),
        "url": _trim(tree.find(".//enlace")),
        "elaborado": _trim(tree.find("elaborado")),
        "nombre": _trim(tree.find("nombre")),
        "provincia": _trim(tree.find("provincia")),
    }

    def _add(f: str, p: str, field: str, val):
        if val is None:
            return
        if p is None:
            p = "00-24"
        if p not in OK_P:
            raise ValueError(f"periodo/hora={p}")
        key = f"{f} {p}"
        if key not in pre:
            pre[key] = {}
        if field in pre[key]:
            raise ValueError(f"{key} = {val}")
        pre[key][field] = val

    for campo in tree.findall(".//dia/*"):
        if campo.tag not in OK_CAMPO:
            raise ValueError(campo.tag)

    for dia in tree.findall(".//dia"):
        f = _trim(dia.get('fecha'))
        for k in (
            "prob_precipitacion",
            "cota_nieve_prov",
            "estado_cielo",
            "racha_max",
            "uv_max",
            "viento",
        ):
            for n in dia.findall(f".//{k}"):
                v = _val(n)
                p = _trim(n.get('periodo'))
                _add(f, p, k, v)
        for k in (
            "temperatura",
            "sens_termica",
            "humedad_relativa",
        ):
            for node in dia.findall(f".//{k}"):
                mn = _trim(node.find("minima"))
                mx = _trim(node.find("maxima"))
                p = _trim(n.get('periodo'))
                _add(f, p, k+"_min", mn)
                _add(f, p, k+"_max", mx)

                for n in node.findall("dato"):
                    v = _val(n)
                    p = _trim(n.get('hora'))
                    _add(f, p, k, v)

    obj['prediccion'] = []
    for k, v in pre.items():
        obj['prediccion'].append({
            **{"periodo": k},
            **v
        })
    return obj


class Periodo(NamedTuple):
    label: str
    prob_precipitacion: Optional[int] = None
    cota_nieve_prov: Optional[int] = None
    estado_cielo: Optional[str] = None
    racha_max: Optional[int] = None
    viento: Optional[int] = None
    uv_max: Optional[int] = None
    temperatura_min: Optional[int] = None
    temperatura_max: Optional[int] = None
    sens_termica_min: Optional[int] = None
    sens_termica_max: Optional[int] = None
    humedad_relativa_min: Optional[int] = None
    humedad_relativa_max: Optional[int] = None

    def get_periodo(self):
        arr = tuple(map(int, re.findall(r"\d+", self.label)))
        dt = date(arr[0], arr[1], arr[2])
        return dt, arr[3], arr[4]

    def print(self):
        print(f"Estado del cielo: {self.estado_cielo}")
        print(f"Temp. min./max.:  {self.temperatura} °C")
        print(f"Precipitaciones:  {self.prob_precipitacion} %")
        print(f"Humedad relativa: {self.humedad_relativa} %")
        print(f"Viento:           {self.viento} km/h")

    @property
    def humedad_relativa(self):
        if self.humedad_relativa_max is None or self.humedad_relativa_min is None:
            return None
        if self.humedad_relativa_max == self.humedad_relativa_min:
            return f"{self.humedad_relativa_min}"
        return f"{self.humedad_relativa_min} / {self.humedad_relativa_max}"

    @property
    def temperatura(self):
        t1min = _or(self.temperatura_min, self.sens_termica_min)
        t1max = _or(self.temperatura_max, self.sens_termica_max)
        t2min = _or(self.sens_termica_min, self.temperatura_min)
        t2max = _or(self.sens_termica_max, self.temperatura_max)
        tp = (t1min, t1max, t2min, t2max)
        if tp == (None, None, None, None):
            return None
        if None in tp:
            raise ValueError(self)
        t = []
        if t1min == t1max:
            t.append(f"{t1min}")
        else:
            t.append(f"{t1min} / {t1max}")
        if t1min != t2min and t1max != t2max:
            if t2min == t2max:
                t.append(f"[{t2min}]")
            else:
                t.append(f"[{t2min} / {t2max}]")
        return " ".join(t)

    @classmethod
    def merge(cls, *periodos: Union["Periodo", None]):
        obj = {k: None for k in cls._fields}
        labels = []
        for p in periodos:
            if p is None:
                continue
            ok = False
            aux = p._asdict()
            label = aux.pop('label')
            for k, v in aux.items():
                if v is not None and obj.get(k) is None:
                    logger.debug(f"[{label}] {k} = {v}")
                    ok = True
                    obj[k] = v
            if ok:
                labels.append(label)
        if all(v is None for v in obj.values()):
            return None
        obj['label'] = " - ".join(labels)
        return cls(**obj)


class Hora(NamedTuple):
    label: str
    temperatura: int
    sens_termica: int
    humedad_relativa: int

    def get_periodo(self):
        arr = tuple(map(int, re.findall(r"\d+", self.label)))
        dt = date(arr[0], arr[1], arr[2])
        return dt, arr[3]

    def temp(self):
        if self.temperatura == self.sens_termica:
            return f"{self.temperatura}"
        return f"{self.temperatura} [{self.sens_termica}]"


class Index(NamedTuple):
    p00_06: Optional[Periodo] = None
    p00_12: Optional[Periodo] = None
    p00_24: Optional[Periodo] = None
    p06_12: Optional[Periodo] = None
    p12_18: Optional[Periodo] = None
    p12_24: Optional[Periodo] = None
    p18_24: Optional[Periodo] = None
    h06: Optional[Hora] = None
    h12: Optional[Hora] = None
    h18: Optional[Hora] = None
    h24: Optional[Hora] = None


class Data(NamedTuple):
    id: int
    url: str
    elaborado: str
    nombre: str
    provincia: str
    prediccion: MappingProxyType[str, Index]

    def dump(self):
        out = ROOT_DIR / str(self.id) / f"{self.elaborado}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(_parse_obj(self), f, indent=2)

    @classmethod
    def load(cls, path: str):
        file = Path(path)
        if not file.is_file():
            return None
        with open(file, "r") as f:
            obj = json.load(f)
        if not isinstance(obj, dict):
            raise ValueError(obj)
        prediccion = obj.get("prediccion")
        if not isinstance(prediccion, dict):
            raise ValueError(obj)
        for k, v in list(prediccion.items()):
            if not isinstance(v, dict):
                raise ValueError(obj)
            for kk, vv in list(v.items()):
                if kk[0] == "h":
                    vv = Hora(label=f"{k} {kk}", **vv)
                else:
                    vv = Periodo(label=f"{k} {kk}", **vv)
                v[kk] = vv
            prediccion[k] = Index(**v)
        obj['prediccion'] = MappingProxyType(prediccion)
        return Data(**obj)


class Meteo:
    def __init__(self, id: int | str):
        self.__id = Meteo.parse_id(id)

    @staticmethod
    def parse_id(id: str | int):
        if isinstance(id, int):
            return id
        if not isinstance(id, str):
            raise ValueError(id)
        if id.isdecimal():
            return int(id)
        m = re.match("^http://www\.aemet\.es/xml/municipios/localidad_(\d+)\.xml", id)
        if m:
            return int(m.group(1))
        raise ValueError(id)

    @property
    def id(self):
        self.__id

    @property
    def url(self):
        return f"http://www.aemet.es/xml/municipios/localidad_{self.__id}.xml"

    def __get_json(self):
        with urlopen(self.url) as r:
            body = r.read().decode('ISO-8859-15')
            xml = ET.fromstring(body)
            return xml_to_json(xml)

    @cached_property
    def data(self):
        obj = self.__get_json()
        _id_ = obj['id']
        if _id_ != self.__id:
            raise ValueError(f"{_id_} != {self.__id} {obj}")
        with open("p.json", "w") as f:
            json.dump(obj, f, indent=2)
        dias: dict[str, dict[str, dict[str]]] = {}
        for p in obj['prediccion']:
            periodo: str = p.pop("periodo")
            fch, per = periodo.split()
            if fch not in dias:
                dias[fch] = {}
            if len(per) == 2:
                per = f"h{per}"
            else:
                per = f"p{per}".replace("-", "_")
            if per in dias[fch]:
                raise ValueError(f"{periodo} duplicado")
            if per[0] == 'h':
                p = Hora(label=f"{fch} {per}", **p)
            else:
                p = Periodo(label=f"{fch} {per}", **p)
            dias[fch][per] = p

        for k, v in tuple(dias.items()):
            dias[k] = Index(**v)

        d = Data(
            id=_id_,
            url=obj['url'],
            elaborado=obj['elaborado'],
            nombre=obj['nombre'],
            provincia=obj['provincia'],
            prediccion=MappingProxyType(dict(sorted(dias.items())))
        )
        d.dump()
        return d

    def __get_predccion(self, dt: datetime | date):
        return self.data.prediccion.get(dt.strftime("%Y-%m-%d"))

    def get_dia(self, dt: Optional[datetime | date] = None, tarde: Optional[bool] = None):
        if dt is None:
            dt = datetime.now()
        a = self.__get_predccion(dt-timedelta(days=-1)) or Index()
        h = self.__get_predccion(dt) or Index()
        m = self.__get_predccion(dt+timedelta(days=-1)) or Index()

        if isinstance(dt, date) and not isinstance(dt, datetime):
            if tarde is None:
                return Periodo.merge(
                    h.p00_24,
                    h.p00_12,
                    h.p12_24,
                    h.p06_12,
                    h.p12_18,
                    h.p18_24,
                    h.p00_06
                )
            if tarde is True:
                return Periodo.merge(
                    h.p12_24,
                    h.p12_18,
                    h.p18_24,
                    h.p00_24,
                )
            return Periodo.merge(
                h.p00_12,
                h.p06_12,
                h.p00_06,
                h.p00_24,
            )

        if dt.hour < 3:
            return Periodo.merge(
                h.p00_06,
                h.p00_12,
                h.p00_24,
                a.p12_24
            )
        if dt.hour < 6:
            return Periodo.merge(
                h.p00_06,
                h.p06_12 if dt.hour == 5 else None,
                h.p00_12,
                h.p00_24,
            )
        if dt.hour < 12:
            return Periodo.merge(
                h.p06_12,
                h.p00_12,
                h.p12_18 if dt.hour == 11 else None,
                h.p12_24 if dt.hour == 11 else None,
                h.p00_24,
            )
        if dt.hour < 18:
            return Periodo.merge(
                h.p12_18,
                h.p18_24 if dt.hour == 17 else None,
                h.p12_24,
                h.p00_24,
            )
        if dt.hour <= 24:
            return Periodo.merge(
                h.p18_24,
                m.p00_06 if dt.hour == 24 else None,
                h.p12_24,
                h.p00_24,
            )

    def get_hora(self, dt: Optional[datetime] = None):
        if dt is None:
            dt = datetime.now()
        if dt.hour <= 3:
            ayer = self.__get_predccion(dt-timedelta(days=-1))
            if ayer and ayer.h24:
                return ayer.h24
        hoy = self.__get_predccion(dt)
        if hoy is None:
            return None
        if dt.hour <= 3:
            return hoy.h06
        if dt.hour <= 9:
            return hoy.h06 or hoy.h12
        if dt.hour <= 15:
            return hoy.h12 or hoy.h18
        if dt.hour <= 21:
            return hoy.h18 or hoy.h24
        if dt.hour > 21:
            return hoy.h24

    def print(self, dt: Optional[datetime] = None):
        if dt is None:
            dt = datetime.now()
        ahora = self.__get_line(dt)
        noche = self.__get_line(dt.replace(
            hour=23,
            minute=0,
            second=0,
            microsecond=0
        ))
        if ahora is not None and noche is not None:
            if ahora == noche:
                print(ahora)
            else:
                print("Ahora:", ahora)
                print("Noche:", noche)

        elif noche is not None:
            print("Noche:", noche)

        d1, d2 = self.__get_split_date(dt)
        print("")
        print(_h1(d1.label, w=20))
        d1.print()
        print("")
        print(_h1(d2.label, w=20))
        d2.print()

    def __get_split_date(self, dt: datetime):
        if dt.hour < 12:
            p1 = self.get_dia(dt.date(), tarde=False)
            p2 = self.get_dia(dt.date(), tarde=True)
            p1 = p1._replace(label=None)
            p2 = p2._replace(label=None)
            if p1 == p2:
                return (
                    p1._replace(label="HOY"),
                    self.get_dia(dt.date()+timedelta(days=1))._replace(label="MAÑANA")
                )
            return (
                p1._replace(label="HOY: Mañana"),
                p1._replace(label="HOY: Tarde")
            )

        return (
            self.get_dia(dt)._replace(label="HOY"),
            self.get_dia(dt.date()+timedelta(days=1))._replace(label="MAÑANA")
        )

    def __get_line(self, dt: datetime):
        a = self.get_hora(dt)
        d = self.get_dia(dt)
        ahora = []
        if d:
            ahora.append(d.estado_cielo)
        if a:
            ahora.append(a.temp()+" °C")
        elif d and d.temperatura:
            ahora.append(f"{d.temperatura} °C")
        if d and d.prob_precipitacion:
            ahora.append(f"{d.prob_precipitacion} % lluvia")
        if a and a.humedad_relativa:
            ahora.append(f"{a.humedad_relativa} % humedad")
        elif d and d.humedad_relativa:
            ahora.append(f"{a.humedad_relativa} % humedad")
        if d and d.viento:
            ahora.append(f"{d.viento} km/h viento")
        return ", ".join(x for x in ahora if x is not None)

    def get_timeline(self, dt: Optional[datetime] = None):
        if dt is None:
            dt = datetime.now()
        arr: list[Periodo | Hora] = []
        fch = dt.strftime("%Y-%m-%d")
        hour = dt.hour
        for k, v in self.data.prediccion.items():
            if k < fch:
                continue
            if k > fch:
                arr.extend(v._asdict().values())
                continue
            for kk, vv in v._asdict().items():
                if kk[0] == "h":
                    if int(kk[1:]) >= hour:
                        arr.append(vv)
                    continue
                a, z = map(int, kk[1:].split("_"))
                if a <= hour < z:
                    arr.append(vv)

        def _sort(x: Periodo | Hora):
            isH = isinstance(x, Hora)
            if isH:
                return (isH, x.label)
            fch, p = x.label.split(None, 1)
            a, z = map(int, p[1:].split("_"))
            diff = z-a
            return (isH, fch, a, diff, z)

        return tuple(sorted(
            (x for x in arr if x is not None),
            key=_sort
        ))

    def print_lluvia(self, prob: int, dt: Optional[datetime] = None):
        lluvia: list[tuple[date, int, Periodo]] = []
        for x in m.get_timeline():
            if not isinstance(x, Periodo) or x.prob_precipitacion is None:
                continue
            if x.prob_precipitacion >= prob:
                lluvia.append(x)
        if len(lluvia) == 0:
            return

        def _sort(x: Periodo):
            d, a, z = x.get_periodo()
            return (d, z-a, -x.prob_precipitacion, z, x)
    
        dt_a_z: dict[date, set[tuple[int, int]]] = defaultdict(set)
        ok_lluvia: list[Periodo] = []
        for x in sorted(lluvia, key=_sort):
            d, a, z = x.get_periodo()
            ok = True
            for old_a, old_z in dt_a_z[d]:
                if a <= old_a and old_z <= z:
                    ok = False
            if ok:
                dt_a_z[d].add((a, z))
                ok_lluvia.append(x)

        size = max(map(len, map(str, (x.prob_precipitacion for x in lluvia))))
        line = "{w}-{d:02d} {text} {p:%s}%% {c}" % size
        lines: str = []
        for x in ok_lluvia:
            d, a, z = x.get_periodo()
            text = f"[{a:02d}-{z:02d}]"
            ln = line.format(
                text=text,
                w=WD[d.weekday()],
                a=a,
                z=z,
                d=d.day,
                p=x.prob_precipitacion,
                c=x.estado_cielo or 'lluvia'
            )
            if ln not in lines:
                lines.append(ln)
        print(*lines, sep="\n")


def getLevel(v: int):
    if v == 0:
        return logging.WARNING, "%(levelname)s %(message)s"
    if v == 1:
        return logging.INFO, "%(asctime)s %(levelname)s %(message)s"
    return logging.DEBUG, "%(asctime)s %(levelname)s %(message)s"


if __name__ == "__main__":
    import sys

    DEF_LOCALIDAD = 28079
    parser = argparse.ArgumentParser(
        description='Muestra la predicción del tiempo',
    )
    parser.add_argument(
        '-v',
        '--verbose',
        action='count',
        default=0,
        help='Nivel de log'
    )
    parser.add_argument(
        '--lluvia',
        type=int,
        default=0,
        help='Imprimir solo información de lluvia si supera cierto porcentaje'
    )
    parser.add_argument(
        'localidad',
        type=str,
        nargs='?',
        help=f'id, url al xml o alias (por defecto: {DEF_LOCALIDAD})'
    )

    args = parser.parse_args()

    log_level, log_format = getLevel(args.verbose)

    logging.basicConfig(
        level=log_level,
        format=log_format,
        datefmt="%H:%M:%S"
    )

    m = Meteo(args.localidad or DEF_LOCALIDAD)
    if args.lluvia > 0:
        m.print_lluvia(args.lluvia)
        sys.exit(0)
    m.print()

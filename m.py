
from urllib.request import urlopen
import xml.etree.ElementTree as ET
from typing import NamedTuple, Optional, Any
from functools import cached_property
import re

re_sp = re.compile(r'\s+')


class MinMax(NamedTuple):
    min: int
    max: Optional[int] = None


class Day(NamedTuple):
    fecha: str
    periodo: MinMax
    estado_cielo: str
    temperatura: MinMax
    prob_precipitacion: int
    humedad_relativa: MinMax
    viento: int
    sens_termica: MinMax


class Dato(NamedTuple):
    periodo: MinMax
    valor: Any


def _trim(s: str | ET.Element | None) -> str:
    if isinstance(s, ET.Element):
        s = s.text
    if s is None:
        return None
    s = re_sp.sub(" ", s).strip()
    if len(s) == 0:
        return None
    return s


def _get_periodo(d: ET.Element) -> MinMax:
    p = _trim(d.get('periodo'))
    if p is not None:
        return MinMax(*map(int, p.split('-')))
    h = _trim(d.get('hora'))
    if h is not None:
        return MinMax(int(h), None)
    return MinMax(0, 24)


def _get_val(n: ET.Element):
    p = _get_periodo(n)
    if n.tag == 'estado_cielo':
        v = _trim(n.get('descripcion'))
        return Dato(periodo=p, valor=v) if v else None
    if n.tag == 'viento':
        v = _trim(n.find('.//velocidad'))
        return Dato(periodo=p, valor=int(v)) if v else None
    if n.tag in ('temperatura', 'sens_termica', 'humedad_relativa'):
        arr: list[Dato] = []
        nn = _trim(n.find('.//maxima'))
        nx = _trim(n.find('.//minima'))
        if None not in (nn, nx):
            arr.append(Dato(periodo=p, valor=MinMax(int(nx), int(nn))))
        for h in n.findall('.//dato'):
            v = _trim(h.text)
            if v is not None:
                arr.append(Dato(periodo=_get_periodo(h), valor=int(v)))
        return arr


def _iter(tree: ET.Element, path: str):
    for p in tree.findall(path):
        val = _get_val(p)
        if val is None:
            continue
        if isinstance(val, list):
            for v in val:
                yield v
        else:
            yield val


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


def xml_to_json(tree: ET.Element):
    obj = {
        "id": int(tree.get("id")),
        "url": _trim(tree.find(".//enlace")),
        "elaborado": _trim(tree.find("elaborado")),
        "nombre": _trim(tree.find("nombre")),
        "provincia": _trim(tree.find("provincia")),
    }
    pre = {}

    def _add(f: str, p: str, field: str, val):
        if val is None:
            return
        if p is None:
            p = "00-24"
        key = f"{f} {p}"
        if key not in pre:
            pre[key] = {}
        if field in pre[key]:
            raise ValueError(f"{key} = {val}")
        pre[key][field] = val

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
                mn = _trim(node.get("minima"))
                mx = _trim(node.get("maxima"))
                p = _trim(n.get('periodo'))
                _add(f, p, k+"_min", mn)
                _add(f, p, k+"_max", mx)

                for n in node.findall("dato"):
                    v = _val(n)
                    p = _trim(n.get('hora'))
                    _add(f, p, k, v)
    obj['prediccion'] = []
    for k, v in pre.items():
        field = "periodo"
        if len(k) == 13:
            field = "hora"
        obj['prediccion'].append({
            **{field: k},
            **v
        })
    return obj


class Meteo:
    def __init__(self, url: str):
        self.__url = url

    def read_xml(self):
        with urlopen(self.__url) as r:
            body = r.read().decode('ISO-8859-15')
            return ET.fromstring(body)

    def read_json(self):
        tree = self.read_xml()
        return xml_to_json(tree)

    @cached_property
    def city(self):
        n = _trim(self.__tree.find('.//nombre').text)
        p = _trim(self.__tree.find('.//provincia').text)
        if None in (n, p):
            return p or n
        if p == n:
            return p
        return f"{p} ({n})"

    @cached_property
    def days(self):
        days: dict[tuple[str, MinMax], Day] = {}
        template = Day(**{k: None for k in Day._fields})

        def _add(f: str, i: MinMax, **kwargs):
            k = (fecha, i)
            val = days.get(k, template)
            days[k] = val._replace(fecha=fecha, periodo=i, **kwargs)

        for d in self.__tree.findall('.//prediccion/dia'):
            fecha = d.get('fecha')
            for val in _iter(d, './/prob_precipitacion'):
                _add(fecha, val.periodo, prob_precipitacion=val.valor)
            for val in _iter(d, './/estado_cielo'):
                _add(fecha, val.periodo, estado_cielo=val.valor)
            for val in _iter(d, './/viento'):
                _add(fecha, val.periodo, viento=val.valor)
            for val in _iter(d, './/temperatura'):
                _add(fecha, val.periodo, temperatura=val.valor)
            for val in _iter(d, './/sens_termica'):
                _add(fecha, val.periodo, sens_termica=val.valor)
            for val in _iter(d, './/humedad_relativa'):
                _add(fecha, val.periodo, humedad_relativa=val.valor)

        return tuple(sorted(set(days.values()), key=lambda d: (d.fecha, d.periodo.min)))


if __name__ == "__main__":
    import json
    m = Meteo("http://www.aemet.es/xml/municipios/localidad_28079.xml")
    with open("p.json", "w") as f:
        json.dump(m.read_json(), f, indent=2)

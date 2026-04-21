
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


class Meteo:
    def __init__(self, url: str):
        self.__tree = self.read_xml(url)

    def read_xml(self, url: str):
        with urlopen(url) as r:
            body = r.read().decode('ISO-8859-15')
            return ET.fromstring(body)

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
    m = Meteo("http://www.aemet.es/xml/municipios/localidad_28079.xml")
    print(m.city)
    print(*m.days, sep="\n")
    periodos: set[MinMax] = set()
    for d in m.days:
        periodos.add(d.periodo)
    print(*sorted(periodos, key=lambda p: (p.min, p.max or p.min)), sep="\n")

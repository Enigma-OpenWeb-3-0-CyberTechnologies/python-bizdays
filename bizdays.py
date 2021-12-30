
import os
import re
from datetime import datetime, date, timedelta
from itertools import cycle


options = {}


D1 = timedelta(1)


def isstr(d):
    return isinstance(d, str)


def isoornot(dt, iso):
    return dt if not iso else dt.isoformat()


class DateOutOfRange(Exception):
    pass


def find_date_pos(col, dt):
    beg = 0
    end = len(col)
    while (end - beg) > 1:
        mid = int((end + beg)/2)
        if dt > col[mid]:
            beg = mid
        elif dt < col[mid]:
            end = mid
        else:
            return mid
    return beg


def daterangecheck(func):
    def handler(self, dt, *args):
        dt = Date(dt).date
        if dt > self.enddate or dt < self.startdate:
            raise DateOutOfRange('Given date out of calendar range')
        return func(self, dt, *args)
    return handler


def load_holidays(fname, format='%Y-%m-%d'):
    if not os.path.exists(fname):
        raise Exception('Invalid calendar specification: \
        file not found (%s)' % fname)
    _holidays = []
    with open(fname) as fcal:
        for cal_reg in fcal:
            cal_reg = cal_reg.strip()
            if cal_reg == '':
                continue
            _holidays.append(Date(cal_reg, format=format).date)
    return _holidays


class DateIndex(object):
    WEEKDAYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')

    def __init__(self, holidays, startdate, enddate, weekdays):
        self._index = {}
        self._bizdays = []
        self._days = []
        self._years = {}
        self._weekdays = {}
        self.startdate = Date(startdate).date
        self.enddate = Date(enddate).date
        self.weekdays = weekdays
        self.holidays = [Date(d).date for d in holidays]

        dts = []
        dt = self.startdate
        while dt <= self.enddate:
            dts.append(dt)
            dt = dt + D1

        w = 0
        c = 1
        for dt in dts:
            is_hol = dt in self.holidays or dt.weekday() in weekdays
            if not is_hol:
                w += 1
                self._bizdays.append(dt)
            self._index[dt] = [w, c, is_hol, None]
            c += 1

        max_w = self._index[self.enddate][0]
        w = max_w + 1
        for dt in reversed(dts):
            is_hol = self._index[dt][2]
            if not is_hol:
                w -= 1
            self._index[dt][3] = min(w, max_w)

        for dt in dts:
            # ----
            ix = self._index[dt]
            col = self._years.get(dt.year, [])
            _ = (dt, dt.month, dt.weekday(), ix[2], ix[1], ix[0], ix[3])
            col.append(_)
            # col.append((dt, dt.month, dt.weekday(), is_hol, c, w))
            self._years[dt.year] = col
            col = self._weekdays.get(dt.weekday(), [])
            col.append(dt)
            self._weekdays[dt.weekday()] = col
            self._days.append(dt)
            # ----

    @daterangecheck
    def _getpos(self, dt):
        return self._index[dt][0] - 1

    @daterangecheck
    def offset(self, dt, n):
        if n > 0:
            pos = self._index[dt][0] - 1 + n
        elif n < 0:
            pos = self._index[dt][3] - 1 + n
        else:
            return dt
        return self._bizdays[pos]

    @daterangecheck
    def following(self, dt):
        if not self._index[dt][2]:
            return dt
        else:
            return self.following(dt + D1)

    @daterangecheck
    def modified_following(self, dt):
        dtx = self.following(dt)
        if dtx.month != dt.month:
            dtx = self.preceding(dt)
        return dtx

    @daterangecheck
    def preceding(self, dt):
        if not self._index[dt][2]:
            return dt
        else:
            return self.preceding(dt - D1)

    @daterangecheck
    def modified_preceding(self, dt):
        dtx = self.preceding(dt)
        if dtx.month != dt.month:
            dtx = self.following(dt)
        return dtx

    def seq(self, dt1, dt2):
        dt1 = Date(dt1).date
        dt2 = Date(dt2).date
        if dt1 > self.enddate or dt1 < self.startdate:
            raise DateOutOfRange('Given date out of calendar range')
        if dt2 > self.enddate or dt2 < self.startdate:
            raise DateOutOfRange('Given date out of calendar range')
        if self._index[dt1][2]:
            _ = 'Cannot start a sequence of working days with a ' + \
                'nonworking day: '
            raise ValueError(_ + dt1.isoformat())
        if self._index[dt2][2]:
            _ = 'Cannot end a sequence of working days with a nonworking day: '
            raise ValueError(_ + dt2.isoformat())
        pos1 = self._getpos(dt1)
        pos2 = self._getpos(dt2) + 1
        return self._bizdays[pos1:pos2]

    @daterangecheck
    def get(self, dt):
        return self._index[dt]

    def getbizdays(self, year, month=None):
        if month:
            return sum(not d[3] for d in self._years[year] if d[1] == month)
        else:
            return sum(not d[3] for d in self._years[year])

    def getdate(self, expr, year, month=None):
        tok = expr.split()
        if len(tok) == 2:
            n = self._getnth(tok[0])
            if tok[1] == 'day':
                return self._getnthday(n, year, month)
            elif tok[1] == 'bizday':
                return self._getnthbizday(n, year, month)
            elif tok[1] in self.WEEKDAYS:
                return self._getnthweekday(n, tok[1], year, month)
            else:
                raise ValueError('Invalid day:', tok[1])
        elif len(tok) == 5:
            n = self._getnth(tok[3])
            if tok[4] == 'day':
                pos = self._getnthdaypos(n, year, month)
            elif tok[4] == 'bizday':
                pos = self._getnthbizdaypos(n, year, month)
            else:
                raise ValueError('Invalid reference day:', tok[4])
            m = {'before': -1, 'after': 1}.get(tok[2], 0)
            if not m:
                raise ValueError('Invalid operator:', tok[2])
            n = self._getnthpos(tok[0])*m
            if tok[1] == 'day':
                return self._getnthday_beforeafter(n, pos)
            elif tok[1] == 'bizday':
                return self._getnthbizday_beforeafter(n, pos)
            elif tok[1] in self.WEEKDAYS:
                return self._getnthweekday_beforeafter(n, tok[1], pos)
            else:
                raise ValueError('Invalid day:', tok[1])

    def _getnthpos(self, nth):
        if nth == 'first':
            return 1
        elif nth == 'second':
            return 2
        elif nth == 'third':
            return 3
        elif nth == 'last':
            return 1
        elif nth[-2:] in ('th', 'st', 'nd', 'rd'):
            return int(nth[:-2])
        else:
            raise ValueError('invalid nth:', nth)

    def _getnth(self, nth):
        if nth == 'first':
            return 1
        elif nth == 'second':
            return 2
        elif nth == 'third':
            return 3
        elif nth == 'last':
            return -1
        elif nth[-2:] in ('th', 'st', 'nd', 'rd'):
            return int(nth[:-2])
        else:
            raise ValueError('invalid nth:', nth)

    def _getnthdaypos(self, n, year, month=None):
        n = n - 1 if n > 0 else n
        if month:
            pos = [(d[4]-1, d[5]-1, d[0], d[6]-1) for d in self._years[year]
                   if d[1] == month]
            return pos[n]
        else:
            return (
                self._years[year][n][4] - 1,
                self._years[year][n][5] - 1,
                self._years[year][n][0],
                self._years[year][n][6]
            )

    def _getnthbizdaypos(self, n, year, month=None):
        n = n - 1 if n > 0 else n
        if month:
            col = [(d[4]-1, d[5]-1, d[0], d[6]-1) for d in self._years[year]
                   if not d[3] and d[1] == month]
        else:
            col = [(d[4]-1, d[5]-1, d[0], d[6]-1) for d in self._years[year]
                   if not d[3]]
        return col[n]

    def _getnthweekdaypos(self, n, weekday, year, month=None):
        n = n - 1 if n > 0 else n
        if month:
            col = [(d[4]-1, d[5]-1, d[0], d[6]-1) for d in self._years[year]
                   if self.WEEKDAYS[d[2]] == weekday and d[1] == month]
        else:
            col = [(d[4]-1, d[5]-1, d[0], d[6]-1) for d in self._years[year]
                   if self.WEEKDAYS[d[2]] == weekday]
        return col[n]

    def _getnthday_beforeafter(self, n1, pos):
        pos = pos[0] + n1
        return self._days[pos]

    def _getnthbizday_beforeafter(self, n1, pos):
        if n1 > 0:
            pos = pos[1] + n1
        else:
            pos = pos[3] + n1
        return self._bizdays[pos]

    def _getnthweekday_beforeafter(self, n1, weekday, pos):
        dt = pos[2]
        wday = self.WEEKDAYS.index(weekday)
        pos = find_date_pos(self._weekdays[wday], dt)
        if dt.weekday() != wday:
            n1 = n1 + 1 if n1 < 0 else n1
        return self._weekdays[wday][pos + n1]

    def _getnthday(self, n, year, month=None):
        pos = self._getnthdaypos(n, year, month)[0]
        return self._days[pos]

    def _getnthbizday(self, n, year, month=None):
        pos = self._getnthbizdaypos(n, year, month)[1]
        return self._bizdays[pos]

    def _getnthweekday(self, n, weekday, year, month=None):
        n = n - 1 if n > 0 else n
        if month:
            col = [d[0] for d in self._years[year]
                   if self.WEEKDAYS[d[2]] == weekday and d[1] == month]
        else:
            col = [d[0] for d in self._years[year]
                   if self.WEEKDAYS[d[2]] == weekday]
        return col[n]

    def __getitem__(self, dt):
        return self.get(dt)


class Date(object):
    def __init__(self, d=None, format='%Y-%m-%d'):
        d = d if d else date.today()
        if isstr(d):
            d = datetime.strptime(d, format).date()
        elif isinstance(d, datetime):
            d = d.date()
        elif isinstance(d, Date):
            d = d.date
        elif isinstance(d, date):
            pass
        else:
            raise ValueError()
        self.date = d

    def format(self, fmts='%Y-%m-%d'):
        return datetime.strftime(self.date, fmts)

    def __gt__(self, other):
        return self.date > other.date

    def __ge__(self, other):
        return self.date >= other.date

    def __lt__(self, other):
        return self.date < other.date

    def __le__(self, other):
        return self.date <= other.date

    def __eq__(self, other):
        return self.date == other.date

    def __repr__(self):
        return self.format()

    __str__ = __repr__


class Calendar(object):
    _weekdays = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday',
                 'Saturday', 'Sunday')

    def __init__(self, holidays=[], weekdays=[], startdate=None, enddate=None,
                 name=None, adjust_from='next', adjust_to='previous',
                 financial=True):
        self.financial = financial
        self.name = name
        self._holidays = [Date(d) for d in holidays]
        self._nonwork_weekdays = [
            [w[:3].lower() for w in self._weekdays].index(wd[:3].lower())
            for wd in weekdays]
        if len(self._holidays):
            if startdate:
                self._startdate = Date(startdate)
            else:
                self._startdate = min(self._holidays)
            if enddate:
                self._enddate = Date(enddate)
            else:
                self._enddate = max(self._holidays)
        else:
            if startdate:
                self._startdate = Date(startdate)
            else:
                self._startdate = Date('1970-01-01')
            if enddate:
                self._enddate = Date(enddate)
            else:
                self._enddate = Date('2071-01-01')
        self._index = DateIndex(self._holidays, self._startdate, self._enddate,
                                self._nonwork_weekdays)
        self.vec = VectorizedOps(self)
        if adjust_from == 'next':
            self.__adjust_from = self.__adjust_next
        elif adjust_from == 'previous':
            self.__adjust_from = self.__adjust_previous
        else:
            self.__adjust_from = lambda x: x
        if adjust_to == 'previous':
            self.__adjust_to = self.__adjust_previous
        elif adjust_to == 'next':
            self.__adjust_to = self.__adjust_next
        else:
            self.__adjust_to = lambda x: x

    def __get_weekdays(self):
        return tuple(self._weekdays[nwd] for nwd in self._nonwork_weekdays)
    weekdays = property(__get_weekdays)

    def __get_startdate(self):
        return self._startdate.date
    startdate = property(__get_startdate)

    def __get_enddate(self):
        return self._enddate.date
    enddate = property(__get_enddate)

    def __get_holidays(self):
        return [d.date for d in self._holidays]
    holidays = property(__get_holidays)

    def bizdays(self, date_from, date_to):
        if isseq(date_from) or isseq(date_to):
            return list(self.vec.bizdays(date_from, date_to))
        else:
            if date_from > date_to:
                _from, _to = date_to, date_from
            else:
                _from, _to = date_from, date_to
            d1 = self.__adjust_from(_from)
            d2 = self.__adjust_to(_to)
            dif = self._index[d2][0] - self._index[d1][0]
            rdif = self._index[d2][3] - self._index[d1][3]
            bdays = min(dif, rdif)
            if date_from > date_to:
                bdays = -bdays
            if self.financial:
                return bdays
            else:
                if bdays >= 0:
                    return bdays + 1
                else:
                    return bdays - 1

    def isbizday(self, dt):
        if isseq(dt):
            return list(self.vec.isbizday(dt))
        else:
            return not self._index[dt][2]

    def __adjust_next(self, dt):
        return Date(self._index.following(dt))

    def adjust_next(self, dt, iso=False):
        if isseq(dt):
            return list(self.vec.adjust_next(dt, iso))
        else:
            dt = self.__adjust_next(dt)
            return dt.date if not iso else str(dt)

    following = adjust_next

    def modified_following(self, dt, iso=False):
        if isseq(dt):
            return list(self.vec.modified_following(dt, iso))
        else:
            dtx = self._index.modified_following(dt)
            return dtx.date if not iso else str(dtx)

    def __adjust_previous(self, dt):
        return Date(self._index.preceding(dt))

    def adjust_previous(self, dt, iso=False):
        if isseq(dt):
            return list(self.vec.adjust_previous(dt, iso))
        else:
            dt = self.__adjust_previous(dt)
            return dt.date if not iso else str(dt)

    preceding = adjust_previous

    def modified_preceding(self, dt, iso=False):
        if isseq(dt):
            return list(self.vec.modified_preceding(dt, iso))
        else:
            dtx = self._index.modified_preceding(dt)
            return dtx.date if not iso else str(dtx)

    def seq(self, date_from, date_to, iso=False):
        _from = self.__adjust_from(date_from)
        _to = self.__adjust_to(date_to)
        if _from > _to:
            raise ValueError("The first date must be before the second.")
        return (isoornot(dt, iso) for dt in self._index.seq(_from, _to))

    def offset(self, dt, n, iso=False):
        if isseq(dt) or isseq(n):
            return list(self.vec.offset(dt, n, iso))
        else:
            return isoornot(self._index.offset(dt, n), iso)

    def getdate(self, expr, year, month=None, iso=False, adjust=None):
        dt = self._index.getdate(expr, year, month)
        if adjust == 'next':
            dt = self.__adjust_next(dt)
        elif adjust == 'previous':
            dt = self.__adjust_previous(dt)
        else:
            dt = Date(dt)
        return dt.date if not iso else str(dt)

    def getbizdays(self, year, month=None):
        return self._index.getbizdays(year, month)

    @classmethod
    def load(cls, fname):
        if not os.path.exists(fname):
            raise Exception('Invalid calendar specification: \
            file not found (%s)' % fname)
        name = os.path.split(fname)[-1]
        if name.endswith('.cal'):
            name = name.replace('.cal', '')
        else:
            name = None
        w = '|'.join(w.lower() for w in cls._weekdays)
        wre = '^%s$' % w
        _holidays = []
        _nonwork_weekdays = []
        with open(fname) as fcal:
            for cal_reg in fcal:
                cal_reg = cal_reg.strip()
                if cal_reg == '':
                    continue
                if re.match(wre, cal_reg.lower()):
                    _nonwork_weekdays.append(cal_reg)
                elif re.match(r'^\d\d\d\d-\d\d-\d\d$', cal_reg):
                    _holidays.append(Date(cal_reg))
        return Calendar(_holidays, weekdays=_nonwork_weekdays, name=name)

    def __str__(self):
        return '''Calendar: {0}
Start: {1}
End: {2}
Holidays: {3}
Financial: {4}'''.format(self.name, self.startdate, self.enddate,
                         len(self._holidays), self.financial)

    __repr__ = __str__


def isseq(seq):
    if isstr(seq):
        return False
    try:
        iter(seq)
    except TypeError:
        return False
    else:
        return True


class VectorizedOps(object):
    def __init__(self, calendar):
        self.cal = calendar

    def isbizday(self, dates):
        return (self.cal.isbizday(dt) for dt in dates)

    def bizdays(self, dates_from, dates_to):
        if not isseq(dates_from):
            dates_from = [dates_from]
        if not isseq(dates_to):
            dates_to = [dates_to]
        lengths = [len(dates_from), len(dates_to)]
        if max(lengths) % min(lengths) != 0:
            raise Exception('from length must be multiple of to length and '
                            'vice-versa')
        if len(dates_from) < len(dates_to):
            dates_from = cycle(dates_from)
        else:
            dates_to = cycle(dates_to)
        return (self.cal.bizdays(_from, _to)
                for _from, _to in zip(dates_from, dates_to))

    def adjust_next(self, dates, iso=False):
        if not isseq(dates):
            dates = [dates]
        return (self.cal.adjust_next(dt, iso=iso) for dt in dates)

    def modified_following(self, dates, iso=False):
        if not isseq(dates):
            dates = [dates]
        return (self.cal.modified_following(dt, iso=iso) for dt in dates)

    def adjust_previous(self, dates, iso=False):
        if not isseq(dates):
            dates = [dates]
        return (self.cal.adjust_previous(dt, iso=iso) for dt in dates)

    def modified_preceding(self, dates, iso=False):
        if not isseq(dates):
            dates = [dates]
        return (self.cal.modified_preceding(dt, iso=iso) for dt in dates)

    def offset(self, dates, ns, iso=False):
        if not isseq(dates):
            dates = [dates]
        if not isseq(ns):
            ns = [ns]
        if len(dates) < len(ns):
            dates = cycle(dates)
        else:
            ns = cycle(ns)
        return (self.cal.offset(dt, n, iso=iso) for dt, n in zip(dates, ns))

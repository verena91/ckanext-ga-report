import re
import uuid

from sqlalchemy import Table, Column, MetaData, ForeignKey
from sqlalchemy import types
from sqlalchemy.sql import select
from sqlalchemy.orm import mapper, relation
from sqlalchemy import func

import ckan.model as model
from ckan.lib.base import *

def make_uuid():
    return unicode(uuid.uuid4())

metadata = MetaData()

class GA_Url(object):

    def __init__(self, **kwargs):
        for k,v in kwargs.items():
            setattr(self, k, v)

url_table = Table('ga_url', metadata,
                      Column('id', types.UnicodeText, primary_key=True,
                             default=make_uuid),
                      Column('period_name', types.UnicodeText),
                      Column('period_complete_day', types.Integer),
                      Column('pageviews', types.UnicodeText),
                      Column('visits', types.UnicodeText),
                      Column('url', types.UnicodeText),
                      Column('department_id', types.UnicodeText),
                      Column('package_id', types.UnicodeText),
                )
mapper(GA_Url, url_table)


class GA_Stat(object):

    def __init__(self, **kwargs):
        for k,v in kwargs.items():
            setattr(self, k, v)

stat_table = Table('ga_stat', metadata,
                  Column('id', types.UnicodeText, primary_key=True,
                         default=make_uuid),
                  Column('period_name', types.UnicodeText),
                  Column('stat_name', types.UnicodeText),
                  Column('key', types.UnicodeText),
                  Column('value', types.UnicodeText), )
mapper(GA_Stat, stat_table)


class GA_Publisher(object):

    def __init__(self, **kwargs):
        for k,v in kwargs.items():
            setattr(self, k, v)

pub_table = Table('ga_publisher', metadata,
                  Column('id', types.UnicodeText, primary_key=True,
                         default=make_uuid),
                  Column('period_name', types.UnicodeText),
                  Column('publisher_name', types.UnicodeText),
                  Column('views', types.UnicodeText),
                  Column('visits', types.UnicodeText),
                  Column('toplevel', types.Boolean, default=False),
                  Column('subpublishercount', types.Integer, default=0),
                  Column('parent', types.UnicodeText),
)
mapper(GA_Publisher, pub_table)


class GA_ReferralStat(object):

    def __init__(self, **kwargs):
        for k,v in kwargs.items():
            setattr(self, k, v)

referrer_table = Table('ga_referrer', metadata,
                      Column('id', types.UnicodeText, primary_key=True,
                             default=make_uuid),
                      Column('period_name', types.UnicodeText),
                      Column('source', types.UnicodeText),
                      Column('url', types.UnicodeText),
                      Column('count', types.Integer),
                )
mapper(GA_ReferralStat, referrer_table)



def init_tables():
    metadata.create_all(model.meta.engine)


cached_tables = {}


def get_table(name):
    if name not in cached_tables:
        meta = MetaData()
        meta.reflect(bind=model.meta.engine)
        table = meta.tables[name]
        cached_tables[name] = table
    return cached_tables[name]


def _normalize_url(url):
    '''Strip off the hostname etc. Do this before storing it.

    >>> normalize_url('http://data.gov.uk/dataset/weekly_fuel_prices')
    '/dataset/weekly_fuel_prices'
    '''
    return '/' + '/'.join(url.split('/')[3:])


def _get_package_and_publisher(url):
    # e.g. /dataset/fuel_prices
    # e.g. /dataset/fuel_prices/resource/e63380d4
    dataset_match = re.match('/dataset/([^/]+)(/.*)?', url)
    if dataset_match:
        dataset_ref = dataset_match.groups()[0]
        dataset = model.Package.get(dataset_ref)
        if dataset:
            publisher_groups = dataset.get_groups('publisher')
            if publisher_groups:
                return dataset_ref,publisher_groups[0].name
        return dataset_ref, None
    else:
        publisher_match = re.match('/publisher/([^/]+)(/.*)?', url)
        if publisher_match:
            return None, publisher_match.groups()[0]
    return None, None

def update_sitewide_stats(period_name, stat_name, data):
    for k,v in data.iteritems():
        item = model.Session.query(GA_Stat).\
            filter(GA_Stat.period_name==period_name).\
            filter(GA_Stat.key==k).\
            filter(GA_Stat.stat_name==stat_name).first()
        if item:
            item.period_name = period_name
            item.key = k
            item.value = v
            model.Session.add(item)
        else:
            # create the row
            values = {'id': make_uuid(),
                     'period_name': period_name,
                     'key': k,
                     'value': v,
                     'stat_name': stat_name
                     }
            model.Session.add(GA_Stat(**values))
        model.Session.commit()


def pre_update_url_stats(period_name):
    model.Session.query(GA_Url).\
            filter(GA_Url.period_name==period_name).delete()
    model.Session.query(GA_Url).\
            filter(GA_Url.period_name=='All').delete()


def update_url_stats(period_name, period_complete_day, url_data):
    '''
    Given a list of urls and number of hits for each during a given period,
    stores them in GA_Url under the period and recalculates the totals for
    the 'All' period.
    '''
    for url, views, visits in url_data:
        package, publisher = _get_package_and_publisher(url)


        item = model.Session.query(GA_Url).\
            filter(GA_Url.period_name==period_name).\
            filter(GA_Url.url==url).first()
        if item:
            item.pageviews = item.pageviews + views
            item.visits = item.visits + visits
            if not item.package_id:
                item.package_id = package
            if not item.department_id:
                item.department_id = publisher
            model.Session.add(item)
        else:
            values = {'id': make_uuid(),
                      'period_name': period_name,
                      'period_complete_day': period_complete_day,
                      'url': url,
                      'pageviews': views,
                      'visits': visits,
                      'department_id': publisher,
                      'package_id': package
                     }
            model.Session.add(GA_Url(**values))
        model.Session.commit()

        if package:
            old_pageviews, old_visits = 0, 0
            old = model.Session.query(GA_Url).\
                filter(GA_Url.period_name=='All').\
                filter(GA_Url.url==url).all()
            old_pageviews = sum([int(o.pageviews) for o in old])
            old_visits = sum([int(o.visits) for o in old])

            entries = model.Session.query(GA_Url).\
                filter(GA_Url.period_name!='All').\
                filter(GA_Url.url==url).all()
            values = {'id': make_uuid(),
                      'period_name': 'All',
                      'period_complete_day': 0,
                      'url': url,
                      'pageviews': sum([int(e.pageviews) for e in entries]) + old_pageviews,
                      'visits': sum([int(e.visits) for e in entries]) + old_visits,
                      'department_id': publisher,
                      'package_id': package
                     }

            model.Session.add(GA_Url(**values))
            model.Session.commit()




def update_social(period_name, data):
    # Clean up first.
    model.Session.query(GA_ReferralStat).\
        filter(GA_ReferralStat.period_name==period_name).delete()

    for url,data in data.iteritems():
        for entry in data:
            source = entry[0]
            count = entry[1]

            item = model.Session.query(GA_ReferralStat).\
                filter(GA_ReferralStat.period_name==period_name).\
                filter(GA_ReferralStat.source==source).\
                filter(GA_ReferralStat.url==url).first()
            if item:
                item.count = item.count + count
                model.Session.add(item)
            else:
                # create the row
                values = {'id': make_uuid(),
                          'period_name': period_name,
                          'source': source,
                          'url': url,
                          'count': count,
                         }
                model.Session.add(GA_ReferralStat(**values))
            model.Session.commit()

def update_publisher_stats(period_name):
    """
    Updates the publisher stats from the data retrieved for /dataset/*
    and /publisher/*. Will run against each dataset and generates the
    totals for the entire tree beneath each publisher.
    """
    toplevel = get_top_level()
    publishers = model.Session.query(model.Group).\
        filter(model.Group.type=='publisher').\
        filter(model.Group.state=='active').all()
    for publisher in publishers:
        views, visits, subpub = update_publisher(period_name, publisher, publisher.name)
        parent, parents = '', publisher.get_groups('publisher')
        if parents:
            parent = parents[0].name
        item = model.Session.query(GA_Publisher).\
            filter(GA_Publisher.period_name==period_name).\
            filter(GA_Publisher.publisher_name==publisher.name).first()
        if item:
            item.views = views
            item.visits = visits
            item.publisher_name = publisher.name
            item.toplevel = publisher in toplevel
            item.subpublishercount = subpub
            item.parent = parent
            model.Session.add(item)
        else:
            # create the row
            values = {'id': make_uuid(),
                     'period_name': period_name,
                     'publisher_name': publisher.name,
                     'views': views,
                     'visits': visits,
                     'toplevel': publisher in toplevel,
                     'subpublishercount': subpub,
                     'parent': parent
                     }
            model.Session.add(GA_Publisher(**values))
        model.Session.commit()


def update_publisher(period_name, pub, part=''):
    views,visits,subpub = 0, 0, 0
    for publisher in go_down_tree(pub):
        subpub = subpub + 1
        items = model.Session.query(GA_Url).\
                filter(GA_Url.period_name==period_name).\
                filter(GA_Url.department_id==publisher.name).all()
        for item in items:
            views = views + int(item.pageviews)
            visits = visits + int(item.visits)

    return views, visits, (subpub-1)


def get_top_level():
    '''Returns the top level publishers.'''
    return model.Session.query(model.Group).\
           outerjoin(model.Member, model.Member.table_id == model.Group.id and \
                     model.Member.table_name == 'group' and \
                     model.Member.state == 'active').\
           filter(model.Member.id==None).\
           filter(model.Group.type=='publisher').\
           order_by(model.Group.name).all()

def get_children(publisher):
    '''Finds child publishers for the given publisher (object). (Not recursive)'''
    from ckan.model.group import HIERARCHY_CTE
    return model.Session.query(model.Group).\
           from_statement(HIERARCHY_CTE).params(id=publisher.id, type='publisher').\
           all()

def go_down_tree(publisher):
    '''Provided with a publisher object, it walks down the hierarchy and yields each publisher,
    including the one you supply.'''
    yield publisher
    for child in get_children(publisher):
        for grandchild in go_down_tree(child):
            yield grandchild

def delete(period_name):
    '''
    Deletes table data for the specified period, or specify 'all'
    for all periods.
    '''
    for object_type in (GA_Url, GA_Stat, GA_Publisher, GA_ReferralStat):
        q = model.Session.query(object_type)
        if period_name != 'all':
            q = q.filter_by(period_name=period_name)
        q.delete()
    model.Session.commit()

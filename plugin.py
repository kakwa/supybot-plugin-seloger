###
# Copyright (c) 2013, Pierre-Francois Carpentier
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###

from pyasciigraph import Pyasciigraph 
import os
import time
from lxml import etree
import threading
import md5
import unicodedata
import datetime
import itertools
import re
import supybot.utils as utils
import supybot.ircdb as ircdb
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.ircmsgs as ircmsgs
import supybot.world as world

class SqliteSeLogerDB(object):
    """This Class is the backend of the plugin,
    it handles the database, its creation, its updates,
    it also provides methods to get the ads information
    """

    def __init__(self, log, filename='db.seloger'):
        self.dbs = ircutils.IrcDict()
        self.filename = filename
        self.log = log
        #the elements we get from the xml
        self.val_xml = (
            'idTiers', 
            'idAnnonce',
            'idPublication', 
            'idTypeTransaction', 
            'idTypeBien',
            'dtFraicheur', 
            'dtCreation', 
            'titre', 
            'libelle', 
            'proximite', 
            'descriptif', 
            'prix',
            'prixUnite', 
            'prixMention', 
            'nbPiece', 
            'nbChambre', 
            'surface', 
            'surfaceUnite', 
            'idPays', 
            'pays', 
            'cp', 
            'ville', 
            'nbPhotos',
            'firstThumb',
            'permaLien',
            'latitude',
            'longitude',
            'llPrecision'
        ) 
        self.val_xml_count = len(self.val_xml)
        #the primary key of the results table
        self.primary_key = 'idAnnonce'

    def _dict_factory(self, cursor, row):
        """just a small trick to get returns from the
        searches inside the database as dictionnaries
        """
        d = {}
        for idx,col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

    def close(self):
        """function closing the database cleanly
        """
        for db in self.dbs.itervalues():
            db.close()

    def _getDb(self):
        """this function returns a database connexion, if the
        database doesn't exist, it creates it.
        no argument.
        """
        try:
            import sqlite3
        except ImportError:
            raise callbacks.Error, 'You need to have sqlite3 installed to ' \
                                   'use SeLoger.'
        filename = 'db.seloger'

        if filename in self.dbs:
            return self.dbs[filename]
        if os.path.exists(filename):
            self.dbs[filename] = sqlite3.connect(
                filename, check_same_thread = False
                )

            return self.dbs[filename]
        db = sqlite3.connect(filename, check_same_thread = False)
        self.dbs[filename] = db
        cursor = db.cursor()

        #initialisation of the searches table 
        #(contains the searches entered by each user) 
        #search_id: the id of the search 
        #owner_id: the id of the user who entered the search
        #flag_active: a flag set to 1 when the search is active, 
        #             0 when it's not (not in use)
        #cp: the postal code
        #min_surf: minimum surface of the annonce
        #max_price: maximum rent
        #ad_type: type of the ad (1 -> rent, 2 -> sell)
        cursor.execute("""CREATE TABLE searches (
                          search_id TEXT PRIMARY KEY,
                          owner_id TEXT, 
                          flag_active INTEGER,
                          cp TEXT,
                          min_surf TEXT,
                          max_price TEXT,
                          ad_type TEXT,
                          nb_pieces TEXT,
                          UNIQUE (search_id) ON CONFLICT IGNORE)"""
                      )

        #mapping between a search result and a user (n to n mapping)
        #idAnnonce: the id of on annonce
        #owner_id: the id of an owner
        #flag_shown: a flag set to 0 when the annonce was already 
        #           presented to owner_id, 0 if not
        cursor.execute("""CREATE TABLE map (
                          uniq_id TEXT PRIMARY KEY,
                          idAnnonce TEXT,
                          flag_shown INT,
                          ad_type TEXT,
                          owner_id TEXT,
                          UNIQUE (uniq_id) ON CONFLICT IGNORE)"""
                      )

        #generation of the results table (contains the ads info)
        #first: generate the string of fields from self.val_xml
        table_results = ''
        for val in self.val_xml:
            if val == self.primary_key:
                table_results = table_results + val \
                                + ' TEXT PRIMARY KEY, '
            else:
                table_results = table_results + val \
                                + ' TEXT, '

        #finally: creation of the table
        cursor.execute("""CREATE TABLE results (
                          %s
                          UNIQUE (idAnnonce)ON CONFLICT IGNORE)""" % 
                          table_results 
                      )

        db.commit()
        self.log.info('database %s created',filename)
        return db

    def _get_annonce(self, idAnnonce):
        """backend function getting the information of one ad
           arg 1: the ad unique ID ('idAnnonce') 
        """
        db = self._getDb()
        db.row_factory = self._dict_factory
        cursor = db.cursor()
        cursor.execute(
            """SELECT * FROM results WHERE idAnnonce = (?)""",
            (idAnnonce, )
            )
        return cursor.fetchone()

    def _search_seloger(self, cp, min_surf, max_price, ad_type, owner_id, nb_pieces_min):
        """entry function for getting the ads on seloger.com
        arg 1: the postal code
        arg 2: the minimal surface
        arg 3: the maximum rent
        arg 4: type of the add (1 -> location, 2 -> sell) 
        arg 5: the owner_id of the search (the user making the search)
        arg 6: nb_pieces_min, minimum number of rooms 

        """
        owner_id.lower() 
        #the first url for the search
        nb_pieces_search = ','.join([str(x) for x in range(int(nb_pieces_min), 20)])
        url = 'http://ws.seloger.com/search.xml?cp=' + cp + \
        '&idqfix=1&idtt=' + ad_type + '&idtypebien=1,2&pxmax=' + max_price + \
        '&surfacemin=' + min_surf + '&nb_pieces=' + nb_pieces_search

        #we search all the pages 
        #(the current page gives the next if it exists)
        while url is not None:
                url = self._get(url, ad_type, owner_id)

    def _get(self, url, ad_type, owner_id):
        """
        function getting the xml pages  and putting
        the results inside the database
        arg 1: the url giving the nice xml
        arg 2: the owner_id of the search
        """
        owner_id.lower() 
        db = self._getDb()
        cursor = db.cursor()

        #we try to load the xml page
        try:
            tree = etree.parse(url)
        except:
            #if we have some troubles loading the page
            self.log.warning('could not download %s',url)
            return None
        
        #we get the info from the xml
        root = tree.getroot()
        annonces = root.find('annonces')

        if annonces is None:
            return None

        for annonce in annonces:
            values_list=[]
            for val in self.val_xml:
                #if the value exists we put it in the db
                #if it doesn't we put "Unknown"
                if annonce.find(val) is None or annonce.find(val).text is None:
                    values_list.append(u'Unknown')
                else:
                    values_list.append(unicode(annonce.find(val).text))

            # inserting the ad information inside the table
            # ignore Viager
            if not re.match(r'.*[Vv]iager.*', annonce.find('descriptif').text) and not re.match(r'.*/viagers/.*', annonce.find('permaLien').text):
                cursor.execute(
                        "INSERT INTO results VALUES (" + \
                        ','.join(itertools.repeat('?', self.val_xml_count)) + ")",
                        tuple(values_list)
                        )

                annonce_id = annonce.find('idAnnonce').text

                #calcul of the uniq id for the mapping between 
                #the searcher and the ad
                uniq_id = md5.new(owner_id + annonce_id).hexdigest()

                #inserting the new ad inside map
                cursor.execute("INSERT INTO map VALUES (?,?,?,?,?)",\
                        (uniq_id, annonce_id, '1', ad_type, owner_id))
                db.commit()

        #if there is another page, we return it, we return None otherwise
        if tree.xpath('//recherche/pageSuivante'):
            return  tree.xpath('//recherche/pageSuivante')[0].text
        else:
            return None

    def _get_date(self, ad):
        """
        function getting the creation date of an ad
        arg 1: ad
        """
        return ad['dtCreation']


    def add_search(self, owner_id, cp, min_surf, max_price, ad_type, nb_pieces_min):
        """this function adds a search inside the database
        arg 1: te owner_id of the new search
        arg 2: the postal code of the new search
        arg 3: the minimal surface
        arg 4: the maximum price
        arg 4: the minimum number of room
        """
        owner_id.lower() 
        db = self._getDb()
        cursor = db.cursor()
        
        #calcul of a unique ID
        search_id = md5.new(owner_id + cp + min_surf + max_price).hexdigest()

        #insertion of the new search parameters
        cursor.execute("INSERT INTO searches VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (search_id, owner_id, '1', cp, min_surf, max_price, ad_type, nb_pieces_min)
            )

        db.commit()

        self.log.info('%s has added a new search', owner_id)
        return search_id

    def do_searches(self):
        """This function plays the searches of every user,
        and puts the infos inside the database.
        no argument
        """
        self.log.info('begin refreshing database')
        db = self._getDb()
        db.row_factory = self._dict_factory
        cursor = db.cursor()
        #we select all the active searches
        cursor.execute("SELECT * FROM searches WHERE flag_active = 1")

        #for each searches we query seloger.com
        for row in cursor.fetchall():
            self._search_seloger(
                row['cp'],row['min_surf'],row['max_price'],row['ad_type'],row['owner_id'],row['nb_pieces']
                )
        self.log.info('end refreshing database')

    def disable_search(self, search_id, owner_id):
        """ this function disable a search
        arg 1: the unique id of the search
        agr 2: the owner_id of the search
        """
        self.log.info('disabling search %s',search_id)
        db = self._getDb()
        db.row_factory = self._dict_factory
        cursor = db.cursor()
        #we delete the given search of the given user
        cursor.execute(
            "DELETE FROM searches WHERE search_id = (?) AND owner_id = (?)",
            (search_id, owner_id)
            )
        db.commit()
        self.log.info('%s has deleted search %s', owner_id, search_id)

    def get_search(self, owner_id):
        """ this function returns the search of a given user
        arg 1: the owner_id
        """
        self.log.info('printing search list of %s', owner_id)
        owner_id.lower() 
        db = self._getDb()
        db.row_factory = self._dict_factory
        cursor = db.cursor()
        #we get all the searches of the given user
        cursor.execute(
            "SELECT * FROM searches WHERE owner_id = (?) AND flag_active = 1",
            (owner_id, )
            )
        self.log.info('%s has queried his searches', owner_id)

        return cursor.fetchall()

    def get_new(self):
        """ this function returns the ads not already printed
        and marks them as "printed".
        no argument
        """
        db = self._getDb()
        db.row_factory = self._dict_factory
        cursor = db.cursor()
        #we get all the new ads
        cursor.execute("SELECT * FROM map WHERE flag_shown = 1")

        return_annonces=[]
        for row in cursor.fetchall():
            uniq = row['uniq_id']
            #we mark the ad as "read"
            cursor.execute(
                """UPDATE map SET flag_shown = 0 WHERE uniq_id = (?)""",
                (uniq, )
                )
            #we get the infos of the ad
            result = self._get_annonce(row['idAnnonce'])
            #we ad in the result the name of the owner
            result['owner_id'] = row['owner_id']
            return_annonces.append(result)

        db.commit()

        #we sort the ads by date
        return_annonces.sort(key=self._get_date)
        #we get the number of new ads
        number_of_new_ads = str(len(return_annonces))
        self.log.info('printing %s new ads', number_of_new_ads)
        #we return the ads
        return return_annonces

    def get_all(self, owner_id, pc='all', ad_type='1'):
        """ this function returns all the ads of a given user and postal code
        arg1: the owner id
        arg2: the postal code
        """
        db = self._getDb()
        db.row_factory = self._dict_factory
        cursor = db.cursor()
        #we get all the ads of a given user
        cursor.execute("SELECT * FROM map WHERE owner_id = (?) AND ad_type = (?)",
                (owner_id, ad_type)
                )

        return_annonces=[]
        for row in cursor.fetchall():
            uniq = row['uniq_id']

            #we get the infos of the ad
            result = self._get_annonce(row['idAnnonce'])
            #we ad in the result the name of the owner
            result['owner_id'] = row['owner_id']
            #we ad it only if we query all the ads 
            #or it matches the postal code
            if pc == 'all' or result['cp'] == pc:
                return_annonces.append(result)

        #we get the number of ads
        number_of_ads = str(len(return_annonces))
        self.log.info('getting %s ads', number_of_ads)
        #we return the ads
        return return_annonces


class SeLoger(callbacks.Plugin):
    """This plugin search and alerts you in query if 
    new ads are available.
    Use "sladd" for a new search.
    Use "sllist" to list you current search.
    Use "sldisable" to remove an old search."""
    threaded = True

    def __init__(self,irc):
        self.__parent = super(SeLoger, self)
        self.__parent.__init__(irc)
        self.backend = SqliteSeLogerDB(self.log)
        self.gettingLockLock = threading.Lock()
        self.locks = {}
        self.graph = Pyasciigraph()

    ### the external methods

    def sladdrent(self, irc, msg, args, pc, min_surf, max_price, nb_pieces):
        """usage: sladd_rent <postal code> <min surface> <max price> [<nb_pieces>]
        Adds a new rent search for you ( /!\ many messages in the first batch )
        """
        user = irc.msg.nick 
        self._addSearch(str(user), str(pc), str(min_surf), str(max_price), '1', str(nb_pieces))
        msg='Done sladd'
        irc.reply(msg,to=user,private=True)

    sladdrent = wrap(sladdrent, ['int', 'int', 'int', 'int'])

    def slhelp(self, irc, msg, args):
        """usage: slhelp
        display the help for this module
        """
        user = irc.msg.nick
        help_content= {
            'slhelp' : 'Help for this module:',
            'sladdrent <postal code> <min surface> <max price> <min_num_room>': 'Adding a new rent search:',
            'sladdbuy <postal code> <min surface> <max price> <min_num_room>': 'Adding a new buy search:',
            'sllist': 'List your active searches:',
            'sldisable <search ID>': 'Remove the given search (use sllist to get <search ID>):',
            'slstatrent <postal code|\'all\'>': 'Print some stats about \'rent\' searches:',
            'slstatbuy <postal code|\'all\'>': 'print some stats about \'buy\'  searches:',
        }
        for cmd in help_content:
            msg = ircutils.underline(help_content[cmd])
            irc.reply(msg,to=user,private=True)
            msg = ircutils.mircColor(str(cmd), 12)
            irc.reply(msg,to=user,private=True)
            #msg = ''
            #irc.reply(msg,to=user,private=True)

    slhelp = wrap(slhelp)

    def sladdbuy(self, irc, msg, args, pc, min_surf, max_price, nb_pieces):
        """usage: sladd_buy <postal code> <min surface> <max price> [<nb_pieces>]
        Adds a new buy search for you ( /!\ many messages in the first batch )
        """
        user = irc.msg.nick 
        self._addSearch(str(user), str(pc), str(min_surf), str(max_price), '2',
                str(nb_pieces))
        msg='Done sladd'
        irc.reply(msg,to=user,private=True)

    sladdbuy = wrap(sladdbuy, ['int', 'int', 'int', 'int'])

    def sldisable(self, irc, msg, args, id_search):
        """usage: sldisable <id_search>
        Disables a search
        """
        user = irc.msg.nick
        self._disableSearch(user, id_search)
        msg='Done sldisable'
        irc.reply(msg,to=user,private=True)

    sldisable = wrap(sldisable, ['text'])

    def sllist(self, irc, msg, args):
        """usage: sllist
        list all your searches
        """
        user = irc.msg.nick 
        self._listSearch(user, irc)
        msg='Done sllist'
        irc.reply(msg,to=user,private=True)

    sllist = wrap(sllist)

    def slstatrent(self, irc, msg, args, pc):
        """usage: slstatrent <postal code|'all'>
        give you some stats about your rent searches.
        Specify 'all' (no filter), or a specific postal code
        """
        user = irc.msg.nick 
        self._gen_stat_rooms(user, irc, pc, '1')
        self._gen_stat_surface(user, irc, pc, '1')
        msg='Done slstatrent'
        irc.reply(msg,to=user,private=True)

    slstatrent = wrap(slstatrent, ['text'])

    def slstatbuy(self, irc, msg, args, pc):
        """usage: slstatbuy <postal code|'all'>
        give you some stats about your buy searches.
        Specify 'all' (no filter), or a specific postal code
        """
        user = irc.msg.nick 
        self._gen_stat_rooms(user, irc, pc, '2')
        self._gen_stat_surface(user, irc, pc, '2')
        msg='Done slstatbuy'
        irc.reply(msg,to=user,private=True)

    slstatbuy = wrap(slstatbuy, ['text'])

    def colors(self, irc, msg, args):
        for color in range(16):
            msg = ircutils.mircColor(str(color), color)
            irc.reply(msg)

    colors = wrap(colors)

    ### The internal methods

    def _print_stats(self, user, irc, stats):
        """ small function to print a list of line in different color
        """

        #empty line for lisibility
        msg = ' '
        irc.reply(msg,to=user,private=True)

        #list of colors we use (order matters)
        colors = [ 15, 14, 10, 3, 7, 2, 6, 5 ]  
        colors_len = len(colors)
        color = 0

        for line in stats:
            msg = ircutils.mircColor(line, colors[color])
            color = (color + 1) % colors_len
            irc.reply(msg,to=user,private=True)


    def _gen_stat_rooms(self, user, irc, pc, ad_type):
        """internal function generating stats about the number of rooms
        """
        #we get all the ads of the user (with a filter on the postal code)
        ads = self.backend.get_all(user, pc, ad_type)

        #if we have nothing to make stats on
        if len(ads) == 0:
            msg = 'no stats about number of rooms available'
            irc.reply(msg,to=user,private=True)
            return

        number_ads_by_room = {}
        surface_by_room = {}
        price_by_room = {}
        surface_by_room = {}

        list_surface = []
        list_price = []
        list_number = []

        for ad in ads:
            rooms = ad['nbPiece']
            #we increment 'n (rooms)' 
            if rooms in number_ads_by_room:
                number_ads_by_room[rooms] += 1
            else:
                number_ads_by_room[rooms] = 1

            #we add the price to the corresponding field
            if rooms in price_by_room:
                price_by_room[rooms] += float(ad['prix'])
            else:
                price_by_room[rooms] = float(ad['prix'])

            #we add the surface to the corresponding field
            if rooms in surface_by_room:
                surface_by_room[rooms] += float(ad['surface'])
            else:
                surface_by_room[rooms] = float(ad['surface'])
    
        #we generate the list of tuples
        for rooms in sorted(surface_by_room, key=int):

            #the list for number of ads by number of rooms
            list_number.append(( rooms  + ' room(s)',
                number_ads_by_room[rooms]))

            #calcul of the avrage surface for this number of rooms
            surface_by_room[rooms] = surface_by_room[rooms] \
                    / number_ads_by_room[rooms]

            list_surface.append(( rooms  + ' room(s)', 
                int(surface_by_room[rooms]))) 


            #calcul of the avrage price for this number of rooms
            price_by_room[rooms] = price_by_room[rooms] \
                / number_ads_by_room[rooms] 

            list_price.append(( rooms  + ' room(s)', 
                int(price_by_room[rooms])))

        #we print all that
        graph_number = self.graph.graph(u'number of ads by room', list_number)
        self._print_stats(user, irc, graph_number)

        graph_surface =  self.graph.graph(u'surface by room', list_surface)
        self._print_stats(user, irc, graph_surface)

        graph_price = self.graph.graph(u'price by room', list_price)
        self._print_stats(user, irc, graph_price)

    def _get_step(self, ads, id_row, number_of_steps):
        """internal function generating a step for numerical range
        """
        mini = float(ads[0][id_row])
        maxi = float(ads[0][id_row])

        for ad in ads:
            value = float(ad[id_row]) 
            if value > maxi:
                maxi = value
            if value < mini:
                mini = value
        return max(1, int((maxi - mini) / number_of_steps))

    def _gen_stat_surface(self, user, irc, pc, ad_type):
        """internal function generating stats about the surface
        """
        #we get all the ads of the user (with a filter on the postal code)
        ads = self.backend.get_all(user, pc, ad_type)
        #if we have nothing to make stats on
        if len(ads) == 0:
            msg = 'no stats about surface available'
            irc.reply(msg,to=user,private=True)
            return

        number_ads_by_range = {}
        rent_by_range = {}
        price_by_range = {}


        list_rent = []
        list_price = []
        list_number = []

        number_of_steps = 7
        #we calcul the step of the range (max step is 5)
        step = min(self._get_step(ads, 'surface', number_of_steps), 5)

        for ad in ads:
            surface_range = str(int(float(ad['surface']) / step))

            #we count the number of ads by range
            if surface_range in number_ads_by_range:
                number_ads_by_range[surface_range] += 1
            else:
                number_ads_by_range[surface_range] = 1

            #we add the rent to the corresponding range
            if surface_range in rent_by_range:
                rent_by_range[surface_range] += float(ad['prix'])
            else:
                rent_by_range[surface_range] = float(ad['prix'])
    
            #we add the rent per square meter to the corresponding range
            if surface_range in price_by_range:
                price_by_range[surface_range] += float(ad['prix']) \
                        / float(ad['surface'])
            else:
                price_by_range[surface_range] = float(ad['prix']) \
                        / float(ad['surface'])
 
        #we generate the list of tuples to print
        for surface_range in sorted(number_ads_by_range, key=int):
            #calcul of the label
            label = str( int(surface_range) * step) + \
                    ' to ' +\
                    str((int(surface_range) + 1) * step)

            #number of ads by range
            list_number.append(( label,
                number_ads_by_range[surface_range]))

            #calcul of mid rent by range
            mid_rent = int(rent_by_range[surface_range] \
                    / number_ads_by_range[surface_range])

            list_rent.append(( label,
                mid_rent))

            #calcul of mid rent per square meter by range
            mid_price = int(price_by_range[surface_range] \
                    / number_ads_by_range[surface_range])

            list_price.append(( label,
                mid_price))

        #we print all these stats
        graph_number = self.graph.graph(u'number of ads by surface range', list_number)
        self._print_stats(user, irc, graph_number)

        graph_rent =  self.graph.graph(u'price by surface range', list_rent)
        self._print_stats(user, irc, graph_rent)

        graph_price = self.graph.graph(u'price per square meter by surface range', list_price)
        self._print_stats(user, irc, graph_price)
 
 
    def __call__(self, irc, msg):
        """black supybot magic... at least for me
        """
        self.__parent.__call__(irc, msg)
        irc = callbacks.SimpleProxy(irc, msg)
        t = threading.Thread(None,self._print, None, (irc,))
        t.start()

    def _update_db(self):
        """direct call to do_search from the backend class
        it gets the new ads from SeLoger
        """
        self.backend.do_searches()

    def _acquireLock(self, url, blocking=True):
        """Lock handler for the threads
        """
        try:
            self.gettingLockLock.acquire()
            try:
                lock = self.locks[url]
            except KeyError:
                lock = threading.RLock()
                self.locks[url] = lock
            return lock.acquire(blocking=blocking)
        finally:
            self.gettingLockLock.release()

    def _releaseLock(self, url):
        """Lock handler for the threads
        """
        self.locks[url].release()

    def _print(self,irc):
        """This function updates the database 
        and prints any new results to each user
        """
        if self._acquireLock('print', blocking=False):
            self._update_db()
            ads = self.backend.get_new()
            total = len(ads)
            counter = 1
            for ad in ads:
                self._print_ad(ad, irc, counter, total)
                counter += 1
            #we search every 5 minutes
            time.sleep(300)
            self._releaseLock('print')

    def _reformat_date(self, date):
        """small function reformatting the date from SeLoger
        """
        d = datetime.datetime.strptime(date, '%Y-%m-%dT%H:%M:%S')
        return  d.strftime('%d/%m/%Y %H:%M')

    def _print_ad(self,ad,irc, counter, total):
        """this function prints one ad
        """
        #user needs to be an ascii string, not unicode
        user = str(ad['owner_id'])

        #empty line for lisibility
        msg = 'new ad %d/%d' % (counter, total)
        irc.reply(msg,to=user,private=True)

        #printing the pric, number of rooms and surface
        price = ircutils.mircColor('Prix: ' + ad['prix'] + ad['prixUnite'],8)
        rooms  = ircutils.mircColor('Pieces: ' + ad['nbPiece'],4) 
        surface =  ircutils.mircColor(
                        'Surface: ' + ad['surface'] + ad['surfaceUnite'],
                        13
                        )

        msg = price + ' | ' + rooms + ' | ' + surface
        irc.reply(msg,to=user,private=True)

        #printing the city, the postal code and date of the ad
        city = ircutils.mircColor('Ville: ' + ad['ville'], 11)  
        cp = ircutils.mircColor('Code postal: ' + ad['cp'], 12) 
        date = ircutils.mircColor(
                   'Date ajout: ' + self._reformat_date(ad['dtCreation']), 
                   11
                   )


        msg = city + ' | ' + cp + ' | ' + date
        irc.reply(msg,to=user,private=True)

        #printing a googlemaps url to see where it is (data not accurate)
        msg = ircutils.mircColor(
                    'Localisation: https://maps.google.com/maps?q=' \
                            + ad['latitude'] + '+' + ad['longitude'], 
                    3
                    )
        irc.reply(msg,to=user,private=True)

        #printing "Proximite" info
        msg = ircutils.mircColor('Proximite: ' + ad['proximite'],2)
        irc.reply(msg,to=user,private=True)

        #print the description
        msg = u'Description: ' + ad['descriptif']

        #\n creates some mess when we print them, so we remove them.
        msg = re.sub(r'\n', r' ', msg)
        irc.reply(msg,to=user,private=True)

        #printing the permanent link of the ad
        msg = ircutils.mircColor('Lien: ' + ad['permaLien'],9)
        irc.reply(msg,to=user,private=True)

        #one more time, an empty line for lisibility
        msg =  ' '
        irc.reply(msg,to=user,private=True)

        self.log.debug('printing ad %s of %s ', ad['idAnnonce'], user)
 
    def _addSearch(self, user, pc, min_surf, max_price, ad_type, nb_pieces):
        """this function adds a search"""
        self.backend.add_search(user, pc, min_surf, max_price, ad_type,
                nb_pieces)

    def _disableSearch(self, user, id_search):
        """this function disables a search"""
        self.backend.disable_search(id_search,user)

    def _listSearch(self, user, irc):
        """this function list the current searches of a user"""
        searches = self.backend.get_search(user)
        for search in searches:
            id_search = ircutils.mircColor("ID: " + search['search_id'], 8)
            surface = ircutils.mircColor("Surface >= " + search['min_surf'], 4)
            loyer = ircutils.mircColor("Loyer/Prix <= " + search['max_price'], 13)
            cp = ircutils.mircColor("cp == " + search['cp'], 11)
            if search['ad_type'] == '2':
                ad_type = '2 (achat)'
            elif search['ad_type'] == '1':
                ad_type = '1 (location)'
            else:
                ad_type = search['ad_type'] + ' (inconnu)'
            type_ad = ircutils.mircColor("type ad == " + ad_type, 14)
            nb_pieces = ircutils.mircColor("Pieces >= " + search['nb_pieces'], 12)
            msg = id_search + " | " + surface + " | " + loyer + " | " + cp + " | " + type_ad + " | " + nb_pieces
            irc.reply(msg,to=user,private=True)

Class = SeLoger

# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:

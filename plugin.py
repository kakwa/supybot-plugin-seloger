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
    it also provides methods to get the adds information
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
        cursor.execute("""CREATE TABLE searches (
                          search_id TEXT PRIMARY KEY,
                          owner_id TEXT, 
                          flag_active INTEGER,
                          cp TEXT,
                          min_surf TEXT,
                          max_price TEXT,
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
                          owner_id TEXT,
                          UNIQUE (uniq_id) ON CONFLICT IGNORE)"""
                      )

        #generation of the results table (contains the adds info)
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
        """backend function getting the information of one add 
           arg 1: the add unique ID ('idAnnonce') 
        """
        db = self._getDb()
        db.row_factory = self._dict_factory
        cursor = db.cursor()
        cursor.execute(
            """SELECT * FROM results WHERE idAnnonce = (?)""",
            (idAnnonce, )
            )
        return cursor.fetchone()

    def _search_seloger(self, cp, min_surf, max_price, owner_id):
        """entry function for getting the adds on seloger.com
        arg 1: the postal code
        arg 2: the minimal surface
        arg 3: the maximum rent
        arg 4: the owner_id of the search (the user making the search)

        """
        owner_id.lower() 
        #the first url for the search
        url = 'http://ws.seloger.com/search.xml?cp=' + cp + \
        '&idqfix=1&idtt=1&idtypebien=1,2&px_loyerbtw=NAN%2f' + max_price + \
        '&surfacebtw=' + min_surf + '%2fNAN&SEARCHpg=1'

        #we search all the pages 
        #(the current page gives the next if it exists)
        while url is not None:
                url = self._get(url, owner_id)

    def _get(self, url, owner_id):
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

        for annonce in annonces:
            values_list=[]
            for val in self.val_xml:
                #if the value exists we put it in the db
                #if it doesn't we put "Unknown"
                if annonce.find(val) is None or annonce.find(val).text is None:
                    values_list.append(u'Unknown')
                else:
                    values_list.append(unicode(annonce.find(val).text))

            #inserting the add information inside the table
            cursor.execute(
                    "INSERT INTO results VALUES (" + \
                    ','.join(itertools.repeat('?', self.val_xml_count)) + ")",
                    tuple(values_list)
                    )

            annonce_id = annonce.find('idAnnonce').text

            #calcul of the uniq id for the mapping between 
            #the searcher and the add
            uniq_id = md5.new(owner_id + annonce_id).hexdigest()

            #inserting the new add inside map
            cursor.execute("INSERT INTO map VALUES (?,?,?,?)",\
                    (uniq_id, annonce_id, '1', owner_id ))
            db.commit()

        #if there is another page, we return it, we return None otherwise
        if tree.xpath('//recherche/pageSuivante'):
            return  tree.xpath('//recherche/pageSuivante')[0].text
        else:
            return None

    def _get_date(self, add):
        """
        function getting the creation date of an add
        arg 1: add
        """
        return add['dtCreation']


    def add_search(self, owner_id, cp, min_surf, max_price):
        """this function adds a search inside the database
        arg 1: te owner_id of the new search
        arg 2: the postal code of the new search
        arg 3: the minimal surface
        arg 4: the maximum price
        """
        owner_id.lower() 
        db = self._getDb()
        cursor = db.cursor()
        
        #calcul of a unique ID
        search_id = md5.new(owner_id + cp + min_surf + max_price).hexdigest()

        #insertion of the new search parameters
        cursor.execute("INSERT INTO searches VALUES (?, ?, ?, ?, ?, ?)",
            (search_id, owner_id, '1', cp, min_surf, max_price)
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
                row['cp'],row['min_surf'],row['max_price'],row['owner_id']
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
        """ this function returns the adds not already printed
        and marks them as "printed".
        no argument
        """
        db = self._getDb()
        db.row_factory = self._dict_factory
        cursor = db.cursor()
        #we get all the new adds
        cursor.execute("SELECT * FROM map WHERE flag_shown = 1")

        return_annonces=[]
        for row in cursor.fetchall():
            uniq = row['uniq_id']
            #we mark the add as "read"
            cursor.execute(
                """UPDATE map SET flag_shown = 0 WHERE uniq_id = (?)""",
                (uniq, )
                )
            #we get the infos of the add
            result = self._get_annonce(row['idAnnonce'])
            #we add in the result the name of the owner
            result['owner_id'] = row['owner_id']
            return_annonces.append(result)

        db.commit()

        #we sort the adds by date
        return_annonces.sort(key=self._get_date)
        #we get the number of new adds
        number_of_new_adds = str(len(return_annonces))
        self.log.info('printing %s new adds', number_of_new_adds)
        #we return the adds
        return return_annonces

    def get_all(self, owner_id, pc='all'):
        """ this function returns all the adds of a given user and postal code
        arg1: the owner id
        arg2: the postal code
        """
        db = self._getDb()
        db.row_factory = self._dict_factory
        cursor = db.cursor()
        #we get all the adds of a given user
        cursor.execute("SELECT * FROM map WHERE owner_id = (?)",
                (owner_id, )
                )

        return_annonces=[]
        for row in cursor.fetchall():
            uniq = row['uniq_id']

            #we get the infos of the add
            result = self._get_annonce(row['idAnnonce'])
            #we add in the result the name of the owner
            result['owner_id'] = row['owner_id']
            #we add it only if we query all the adds 
            #or it matches the postal code
            if pc == 'all' or result['cp'] == pc:
                return_annonces.append(result)

        #we get the number of adds
        number_of_adds = str(len(return_annonces))
        self.log.info('getting %s adds', number_of_adds)
        #we return the adds
        return return_annonces


class SeLoger(callbacks.Plugin):
    """This plugin search and alerts you in query if 
    new adds are available.
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

    def sladd(self, irc, msg, args, pc, min_surf, max_price):
        """usage: sladd <postal code> <min surface> <max price>
        Adds a new search for you ( /!\ many messages in the first batch )
        """
        user = irc.msg.nick 
        self._addSearch(str(user), str(pc), str(min_surf), str(max_price))
        msg='Done sladd'
        irc.reply(msg,to=user,private=True)

    sladd = wrap(sladd, ['int', 'int', 'int'])

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

    def slstat(self, irc, msg, args, pc):
        """usage: slstat_room <postal code|'all'>
        give you some stats about your searches.
        Specify 'all' (no filter), or a specific postal code
        """
        user = irc.msg.nick 
        self._gen_stat_rooms(user, irc, pc)
        self._gen_stat_surface(user, irc, pc)
        msg='Done slstat'
        irc.reply(msg,to=user,private=True)

    slstat = wrap(slstat, ['text'])

    def colors(self, irc, msg, args):
        for color in range(16):
            msg = ircutils.mircColor(str(color), color)
            irc.reply(msg)

    colors = wrap(colors)

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

    ### The internal methods

    def _gen_stat_rooms(self, user, irc, pc):
        adds = self.backend.get_all(user, pc)
        if len(adds) == 0:
            msg = 'no adds to stats'
            irc.reply(msg,to=user,private=True)
            return
        number_adds_by_room = {}
        surface_by_room = {}
        price_by_room = {}
        surface_by_room = {}

        list_surface = []
        list_price = []
        list_number = []

        for add in adds:
            rooms = add['nbPiece']
            if rooms in number_adds_by_room:
                number_adds_by_room[rooms] += 1
            else:
                number_adds_by_room[rooms] = 1
            if rooms in price_by_room:
                price_by_room[rooms] += float(add['prix'])
            else:
                price_by_room[rooms] = float(add['prix'])
            if rooms in surface_by_room:
                surface_by_room[rooms] += float(add['surface'])
            else:
                surface_by_room[rooms] = float(add['surface'])
    
        for rooms in sorted(surface_by_room, key=int):
            list_number.append(( rooms  + ' room(s)',
                number_adds_by_room[rooms]))

            surface_by_room[rooms] = surface_by_room[rooms] \
                    / number_adds_by_room[rooms]

            list_surface.append(( rooms  + ' room(s)', 
                int(surface_by_room[rooms]))) 


            price_by_room[rooms] = price_by_room[rooms] \
                / number_adds_by_room[rooms] 

            list_price.append(( rooms  + ' room(s)', 
                int(price_by_room[rooms])))

        graph_number = self.graph.graph(u'number of adds by room', list_number)
        self._print_stats(user, irc, graph_number)
        graph_surface =  self.graph.graph(u'surface by room', list_surface)
        self._print_stats(user, irc, graph_surface)
        graph_price = self.graph.graph(u'rent by room', list_price)
        self._print_stats(user, irc, graph_price)

    def _get_step(self, adds, id_row, number_of_steps):
        mini = float(adds[0][id_row])
        maxi = float(adds[0][id_row])

        for add in adds:
            value = float(add[id_row]) 
            if value > maxi:
                maxi = value
            if value < mini:
                mini = value
        return max(1, int((maxi - mini) / number_of_steps))

    def _gen_stat_surface(self, user, irc, pc):
        adds = self.backend.get_all(user, pc)
        if len(adds) == 0:
            msg = 'no adds to stats'
            irc.reply(msg,to=user,private=True)
            return

        number_adds_by_range = {}
        rent_by_range = {}
        price_by_range = {}


        list_rent = []
        list_price = []
        list_number = []

        number_of_steps = 7
        step = min(self._get_step(adds, 'surface', number_of_steps), 5)

        for add in adds:
            surface_range = str(int(float(add['surface']) / step))
            if surface_range in number_adds_by_range:
                number_adds_by_range[surface_range] += 1
            else:
                number_adds_by_range[surface_range] = 1

            if surface_range in rent_by_range:
                rent_by_range[surface_range] += float(add['prix'])
            else:
                rent_by_range[surface_range] = float(add['prix'])
    
            if surface_range in price_by_range:
                price_by_range[surface_range] += float(add['prix']) \
                        / float(add['surface'])
            else:
                price_by_range[surface_range] = float(add['prix']) \
                        / float(add['surface'])
 
        for surface_range in sorted(number_adds_by_range, key=int):
            label = str( int(surface_range) * step) + \
                    ' to ' +\
                    str((int(surface_range) + 1) * step)

            list_number.append(( label,
                number_adds_by_range[surface_range]))

            mid_rent = int(rent_by_range[surface_range] \
                    / number_adds_by_range[surface_range])

            list_rent.append(( label,
                mid_rent))

            mid_price = int(price_by_range[surface_range] \
                    / number_adds_by_range[surface_range])

            list_price.append(( label,
                mid_price))

        graph_number = self.graph.graph(u'number of adds by surface range', list_number)
        self._print_stats(user, irc, graph_number)
        graph_rent =  self.graph.graph(u'rent by surface range', list_rent)
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
        it gets the new adds from SeLoger
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
            for add in self.backend.get_new():
                self._print_add(add,irc)
            #we search every 5 minutes
            time.sleep(300)
            self._releaseLock('print')

    def _reformat_date(self, date):
        """small function reformatting the date from SeLoger
        """
        d = datetime.datetime.strptime(date, '%Y-%m-%dT%H:%M:%S')
        return  d.strftime('%d/%m/%Y %H:%M')

    def _print_add(self,add,irc):
        """this function prints one add
        """
        #user needs to be an ascii string, not unicode
        user = str(add['owner_id'])

        #empty line for lisibility
        msg = ' '
        irc.reply(msg,to=user,private=True)

        #printing the pric, number of rooms and surface
        price = ircutils.mircColor('Prix: ' + add['prix'] + add['prixUnite'],8)
        rooms  = ircutils.mircColor('Pieces: ' + add['nbPiece'],4) 
        surface =  ircutils.mircColor(
                        'Surface: ' + add['surface'] + add['surfaceUnite'],
                        13
                        )

        msg = price + ' | ' + rooms + ' | ' + surface
        irc.reply(msg,to=user,private=True)

        #printing the city, the postal code and date of the add
        city = ircutils.mircColor('Ville: ' + add['ville'], 11)  
        cp = ircutils.mircColor('Code postal: ' + add['cp'], 12) 
        date = ircutils.mircColor(
                   'Date ajout: ' + self._reformat_date(add['dtCreation']), 
                   11
                   )


        msg = city + ' | ' + cp + ' | ' + date
        irc.reply(msg,to=user,private=True)

        #printing a googlemaps url to see where it is (data not accurate)
        msg = ircutils.mircColor(
                    'Localisation: https://maps.google.com/maps?q=' \
                            + add['latitude'] + '+' + add['longitude'], 
                    3
                    )
        irc.reply(msg,to=user,private=True)

        #printing "Proximite" info
        msg = ircutils.mircColor('Proximite: ' + add['proximite'],2)
        irc.reply(msg,to=user,private=True)

        #print the description
        msg = u'Description: ' + add['descriptif']

        #\n creates some mess when we print them, so we remove them.
        msg = re.sub(r'\n', r' ', msg)
        irc.reply(msg,to=user,private=True)

        #printing the permanent link of the add
        msg = ircutils.mircColor('Lien: ' + add['permaLien'],9)
        irc.reply(msg,to=user,private=True)

        #one more time, an empty line for lisibility
        msg =  ' '
        irc.reply(msg,to=user,private=True)

        self.log.debug('printing add %s of %s ', add['idAnnonce'], user)
 
    def _addSearch(self, user, pc, min_surf, max_price):
        """this function adds a search"""
        self.backend.add_search(user, pc, min_surf, max_price)

    def _disableSearch(self, user, id_search):
        """this function disables a search"""
        self.backend.disable_search(id_search,user)

    def _listSearch(self, user, irc):
        """this function list the current searches of a user"""
        searches = self.backend.get_search(user)
        for search in searches:
            id_search = ircutils.mircColor("ID: " + search['search_id'], 8)
            surface = ircutils.mircColor("Surface >= " + search['min_surf'], 4)
            loyer = ircutils.mircColor("Loyer <= " + search['max_price'], 13)
            cp = ircutils.mircColor("cp == " + search['cp'], 11)
            msg = id_search + " | " + surface + " | " + loyer + " | " + cp
            irc.reply(msg,to=user,private=True)

Class = SeLoger

# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:

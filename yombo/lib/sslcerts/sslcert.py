try:  # Prefer simplejson if installed, otherwise json will work swell.
    import simplejson as json
except ImportError:
    import json

import glob
from hashlib import sha256
import os
import os.path
from time import time


# Import twisted libraries
from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks

# Import Yombo libraries
from yombo.core.exceptions import YomboWarning
from yombo.core.log import get_logger
from yombo.utils import save_file, read_file, bytes_to_unicode, unicode_to_bytes
import collections

logger = get_logger('library.sslcerts.sslcert')

class SSLCert(object):
    """
    A class representing a single cert.
    """

    @property
    def previous_status(self):
        return self.human_status(self.previous_is_valid)

    @property
    def current_status(self):
        return self.human_status(self.current_is_valid)

    @property
    def next_status(self):
        return self.human_status(self.next_is_valid)

    def human_status(self, valid):
        if valid is True:
            return "Valid"
        elif valid is False:
            return "Unsigned"
        elif valid is None:
            return "None"

    def __init__(self, source, sslcert, _ParentLibrary):
        """
        :param source: *(source)* - One of: 'sql', 'sslcerts', or 'sqldict'
        :param sslcert: *(dictionary)* - A dictionary of the attributes to setup the class.
        :ivar sslname: *(string)* - The name of base file. The archive name will be based off this.
        :ivar key_size: *(int)* - Size of the key in bits.
        :ivar key_type: *(string)* - Either rsa or dsa.
        """
        self._FullName = 'yombo.gateway.lib.SSLCerts.SSLCert'
        self._Name = 'SSLCerts.SSLCert'
        self._ParentLibrary = _ParentLibrary
        self.source = source

        self.sslname = sslcert.sslname
        self.cn = sslcert.cn
        self.sans = sslcert.sans
        self.cert_fqdn = self._ParentLibrary.fqdn

        self.update_callback = None
        self.update_callback_type = None
        self.update_callback_component = None
        self.update_callback_function = None

        self.key_size = None
        self.key_type = None

        self.cert_previous = None
        self.chain_previous = None
        self.key_previous = None
        self.previous_created = None
        self.previous_expires = None
        self.previous_signed = None
        self.previous_submitted = None
        self.previous_is_valid = None

        self.cert_current = None
        self.chain_current = None
        self.key_current = None
        self.current_created = None
        self.current_expires = None
        self.current_signed = None
        self.current_submitted = None
        self.current_is_valid = None

        self.csr_next = None
        self.cert_next = None
        self.chain_next = None
        self.key_next = None
        self.next_created = None
        self.next_expires = None
        self.next_signed = None
        self.next_submitted = None

        self.next_is_valid = None
        self.next_csr_generation_error_count = 0
        self.next_csr_generation_in_progress = False
        self.next_csr_submit_after_generation = False
        self.csr_last_generated = 0

        self.update_attributes(sslcert)
        self.dirty = False

        self.sync_to_file_calllater = None

        self.check_messages_of_the_unknown()

    @inlineCallbacks
    def start(self):
        # print("!!!!!  starting ssl cert")
        # SQLDict means it came from the database, so only scan the files otherwise.
        if self.source != 'sqldict':
            # print("about to sync from filesystem: %s" % self.key_current)
            yield self.sync_from_filesystem()
            # print("done about to sync from filesystem: %s" % self.key_current)

        self.check_is_valid()
        # print("status: %s" % self.__dict__)

        # check if we need to generate csr, sign csr, or rotate next with current.
        self.check_if_rotate_needed()

    def stop(self):
        """
        Saves the cert meta data to disk...if it's dirty.

        :return:
        """
        self._sync_to_file()


    def update_attributes(self, attributes):
        """
        Update various attributes. Should only be used by the SQLCerts system when loading updated things from
        a library or module.

        The attributes have already been screened by the parent.

        :param attributes:
        :return:
        """
        self.manage_requested = True

        # print("update_attributes: %s" % attributes)
        if 'update_callback' in attributes:
            self.update_callback = attributes['update_callback']
        if 'update_callback_type' in attributes:
            self.update_callback_type = attributes['update_callback_type']
        if 'update_callback_component' in attributes:
            self.update_callback_component = attributes['update_callback_component']
        if 'update_callback_function' in attributes:
            self.update_callback_function = attributes['update_callback_function']

        if 'key_size' in attributes:
            self.key_size = int(attributes['key_size']) if attributes['key_size'] else None
        if 'key_type' in attributes:
            self.key_type = attributes['key_type']

        if 'cert_previous' in attributes:
            self.cert_previous = attributes['cert_previous']
        if 'chain_previous' in attributes:
            self.chain_previous = attributes['chain_previous']
        if 'key_previous' in attributes:
            self.key_previous = attributes['key_previous']
        if 'previous_created' in attributes:
            self.previous_created = int(attributes['previous_created']) if attributes['previous_created'] else None
        if 'previous_expires' in attributes:
            self.previous_expires = int(attributes['previous_expires']) if attributes['previous_expires'] else None
        if 'previous_signed' in attributes:
            self.previous_signed = int(attributes['previous_signed']) if attributes['previous_signed'] else None
        if 'previous_submitted' in attributes:
            self.previous_submitted = int(attributes['previous_submitted']) if attributes['previous_submitted'] else None
        if 'previous_is_valid' in attributes:
            self.previous_is_valid = attributes['previous_is_valid']

        if 'cert_current' in attributes:
            self.cert_current = attributes['cert_current']
        if 'chain_current' in attributes:
            self.chain_current = attributes['chain_current']
        if 'key_current' in attributes:
            self.key_current = attributes['key_current']
        if 'current_created' in attributes:
            self.current_created = int(attributes['current_created']) if attributes['current_created'] else None
        if 'current_expires' in attributes:
            self.current_expires = int(attributes['current_expires']) if attributes['current_expires'] else None
        if 'current_signed' in attributes:
            self.current_signed = int(attributes['current_signed']) if attributes['current_signed'] else None
        if 'current_submitted' in attributes:
            self.current_submitted = int(attributes['current_submitted']) if attributes['current_submitted'] else None
        if 'current_is_valid' in attributes:
            self.current_is_valid = attributes['current_is_valid']

        if 'csr_next' in attributes:
            self.csr_next = attributes['csr_next']
        if 'cert_next' in attributes:
            self.cert_next = attributes['cert_next']
        if 'chain_next' in attributes:
            self.chain_next = attributes['chain_next']
        if 'key_next' in attributes:
            self.key_next = attributes['key_next']
        if 'next_created' in attributes:
            self.next_created = int(attributes['next_created']) if attributes['next_created'] else None
        if 'next_expires' in attributes:
            self.next_expires = int(attributes['next_expires']) if attributes['next_expires'] else None
        if 'next_signed' in attributes:
            self.next_signed = int(attributes['next_signed']) if attributes['next_signed'] else None
        if 'next_submitted' in attributes:
            self.next_submitted = int(attributes['next_submitted']) if attributes['next_submitted'] else None
        if 'next_is_valid' in attributes:
            self.next_is_valid = attributes['next_is_valid']

        self.dirty = True

    def check_if_rotate_needed(self, recursive=None):
        """
        Always make sure the current key is valid. If it's expiring within 60 days, get a new cert.
        However, if the current cert is good, and not expiring soon, we should always have a fresh CSR
        ready to be signed when needed.

        :return:
        """
        logger.debug("Checking if I ({sslname}) need to be updated.", sslname=self.sslname)
        # Look for any tasks to do.
        self.check_updated_fqdn()  # if fqdn of cert doesn't match current, get new cert.

        # 1) See if we need to generate a new cert.
        if self.csr_next is None or self.next_is_valid is None:
            if self.current_is_valid is not True or \
                    self.key_current is None or \
                    self.current_expires is None or \
                    int(self.current_expires) < int(time() + (30 * 24 * 60 * 60)):  # our current cert is bad or expiring
                # print("self.current_is_valid: (should be not True): %s" % self.current_is_valid)
                # print("self.key_current: (should be None): %s" % self.key_current)
                # print("self.current_expires: (should be not NOne): %s" % self.current_expires)
                # print("int(time() + (30 * 24 * 60 * 60)): (should be less then above number): %s" % int(time() + (30 * 24 * 60 * 60)))
                # print("generate new csr...1")
                self.generate_new_csr(submit=True)
            else: # just generate the CSR, no need to sign just yet.  Too soon.
                # print("generate new csr...2")
                self.generate_new_csr(submit=False)
        # 2) If next is valid, then lets rotate into current, doesn't matter if current is good, expired, etc. Just use the next cert.
        elif self.next_is_valid is True:
            self.make_next_be_current()
            self.generate_new_csr(submit=False)
            if recursive is None:
                return self.check_if_rotate_needed(True)
            else:
                raise Exception("Error while rotating next cert to current cert - recursion loop.")
            # # lets check if we need to submit CSR right away:
            # if self.current_is_valid is not True or \
            #         self.key_current is None or \
            #         self.current_expires is None or \
            #         int(self.current_expires) < int(time() + (30 * 24 * 60 * 60)):  # our current cert if bad...lets get a new one ASAP.
            #     print("generate new csr...4")
            #     self.generate_new_csr(submit=True)
            # else:
            #     print("generate new csr...5")
            #     self.generate_new_csr(submit=False)
        # 3) Next cert might be half generated, half signed, maybe waited to be signed, etc. Lets inspect.
        elif self.next_is_valid is False:
            if self.current_is_valid is not True or \
                    self.key_current is None or \
                    self.current_expires is None or \
                    int(self.current_expires) < int(time() + (30 * 24 * 60 * 60)):  # our current cert if bad...lets get a new one ASAP.
                # print("self.current_is_valid: (should be not True): %s" % self.current_is_valid)
                # print("self.key_current: (should be None): %s" % self.key_current)
                # print("self.current_expires: (should be not NOne): %s" % self.current_expires)
                # print("int(time() + (30 * 24 * 60 * 60)): (should be less then above number): %s" % int(time() + (30 * 24 * 60 * 60)))
                # print("should submit csr 10")
                self.submit_csr()
        else:
            raise YomboWarning("next_is_valid is in an unknowns state.")

    def make_next_be_current(self):
        self.migrate_keys("current", "previous")
        self.migrate_keys("next", "current")
        self.update_requester()

    def update_requester(self):
        """
        Used to notify the library or module that requested this certificate that we have an updated
        cert for usage. However, most time, the system will need to be recycled to take affect - we
        leave that up the library or module to ask/notify to recycle the system.

        :return:
        """
        logger.debug("Update any requesters about new certs...")

        method = None
        if self.current_is_valid is not True:
            logger.warn("Asked to update the requester or new cert, but current cert isn't valid!")
            return

        if self.update_callback is not None and isinstance(self.update_callback, collections.Callable):
            method = self.update_callback
        elif self.update_callback_type is not None and \
               self.update_callback_component is not None and \
               self.update_callback_function is not None:
            try:
                method = self._ParentLibrary._Loader.find_function(self.update_callback_type,
                           self.update_callback_component,
                           self.update_callback_function)
            except YomboWarning as e:
                logger.warn("Invalid update_callback information provided: %s" % e)

        if method is not None:
            method(self.get())  # tell the requester that they have a new cert. YAY

    def migrate_keys(self, from_label, to_label):
        if from_label == 'next':
            self.csr_next = None

        setattr(self, "cert_%s" % to_label, getattr(self, "cert_%s" % from_label))
        setattr(self, "chain_%s" % to_label, getattr(self, "chain_%s" % from_label))
        setattr(self, "key_%s" % to_label, getattr(self, "key_%s" % from_label))
        setattr(self, "%s_created" % to_label, getattr(self, "%s_created" % from_label))
        setattr(self, "%s_expires" % to_label, getattr(self, "%s_expires" % from_label))
        setattr(self, "%s_signed" % to_label, getattr(self, "%s_signed" % from_label))
        setattr(self, "%s_submitted" % to_label, getattr(self, "%s_submitted" % from_label))
        setattr(self, "%s_is_valid" % to_label, getattr(self, "%s_is_valid" % from_label))

        setattr(self, "cert_%s" % from_label, None)
        setattr(self, "chain_%s" % from_label, None)
        setattr(self, "key_%s" % from_label, None)
        setattr(self, "%s_created" % from_label, None)
        setattr(self, "%s_expires" % from_label, None)
        setattr(self, "%s_signed" % from_label, None)
        setattr(self, "%s_submitted" % from_label, None)
        setattr(self, "%s_is_valid" % from_label, None)
        self.sync_to_file()

    def clean_section(self, label):
        """
        Used wipe out either 'previous', 'next', or 'current'. This allows to make room or something new.
        :param label:
        :return:
        """
        # print("cleaning section: %s" % label)
        if label == 'next':
            self.csr_next = None
            self.next_csr_generation_error_count

        setattr(self, "cert_%s" % label, None)
        setattr(self, "chain_%s" % label, None)
        setattr(self, "key_%s" % label, None)
        setattr(self, "%s_created" % label, None)
        setattr(self, "%s_expires" % label, None)
        setattr(self, "%s_signed" % label, None)
        setattr(self, "%s_submitted" % label, None)
        setattr(self, "%s_is_valid" % label, None)
        self.sync_to_file() # this will remove the data file, and make a nearly empty meta file.

    def check_messages_of_the_unknown(self):
        if self.sslname in self._ParentLibrary.received_message_for_unknown:
            logger.warn("We have messages for us.  TODO: Implement this.")

    def check_is_valid(self, label=None):
        if label is None:
            labels = ['previous', 'current', 'next']
        else:
            labels = [label]

        for label in labels:
            # print("check is valid for section: %s" % label)
            if getattr(self, "%s_expires" % label) is not None and \
                    int(getattr(self, "%s_expires" % label)) > int(time()) and \
                    getattr(self, "%s_signed" % label) is not None and \
                    getattr(self, "key_%s" % label) is not None and \
                    getattr(self, "cert_%s" % label) is not None and \
                    getattr(self, "chain_%s" % label) is not None:
                setattr(self, "%s_is_valid" % label, True)
            else:
                # print("Setting %s_is_valid to false" % label)
                # print("expires: %s" % getattr(self, "%s_expires" % label))
                # print("time   : %s" % int(time()))
                # print("signed: %s" % getattr(self, "%s_signed" % label))
                # print("key_: %s" % getattr(self, "key_%s" % label))
                # print("cert_: %s" % getattr(self, "cert_%s" % label))
                # print("chain_: %s" % getattr(self, "chain_%s" % label))
                setattr(self, "%s_is_valid" % label, False)

                # print("key_: %s" % getattr(self, "key_%s" % label))
                # print("cert_: %s" % getattr(self, "cert_%s" % label))
                # print("chain_: %s" % getattr(self, "chain_%s" % label))
                if label != "next":
                    if getattr(self, "key_%s" % label) is None or \
                                    getattr(self, "cert_%s" % label) is None or \
                                    getattr(self, "chain_%s" % label) is None or \
                                    getattr(self, "%s_created" % label) is None:
                        # print("calling clean section from check_is_valid for non-next")
                        self.clean_section(label)
                else:
                    # print("csr_next: %s" % getattr(self, "csr_%s" % label))
                    # print("next_created: %s" % getattr(self, "%s_created" % label))
                    if getattr(self, "key_%s" % label) is None or \
                                    getattr(self, "csr_%s" % label) is None or \
                                    getattr(self, "%s_created" % label) is None:
                        # print("calling clean section from check_is_valid_for NEXT")
                        self.clean_section(label)



    @inlineCallbacks
    def sync_from_filesystem(self):
        """
        Reads meta data and items from the file system. This allows us to restore data incase the database
        goes south. This is important since only the gateway has the private key and cannot be recovered.

        :return:
        """
        logger.info("Inspecting file system for certs.")

        for label in ['previous', 'current', 'next']:
            setattr(self, "%s_is_valid" % label, None)

            if os.path.exists('usr/etc/certs/%s.%s.meta' % (self.sslname, label)):
                logger.info("SSL Meta found for: {label} - {sslname}", label=label, sslname=self.sslname)
                file_content = yield read_file('usr/etc/certs/%s.%s.meta' % (self.sslname, label))
                meta = json.loads(file_content)
                # print("meta: %s" % meta)

                csr_read = False
                if label == 'next':
                    logger.debug("Looking for 'next' information.")
                    if os.path.exists('usr/etc/certs/%s.%s.csr.pem' % (self.sslname, label)):
                        if getattr(self, "csr_%s" % label) is None:
                            csr = yield read_file('usr/etc/certs/%s.%s.csr.pem' % (self.sslname, label))
                            if sha256(str(csr).encode('utf-8')).hexdigest() == meta['csr']:
                                csr_read = True
                            else:
                                logger.warn("Appears that the file system has bad meta signatures (csr). Purging.")
                                for file_to_delete in glob.glob("usr/etc/certs/%s.%s.*" % (self.sslname, label)):
                                    logger.warn("Removing bad file: %s" % file_to_delete)
                                    os.remove(file_to_delete)
                                continue

                cert_read = False
                if getattr(self, "cert_%s" % label) is None:
                    if os.path.exists('usr/etc/certs/%s.%s.cert.pem' % (self.sslname, label)):
                        # print("setting cert!!!")
                        cert = yield read_file('usr/etc/certs/%s.%s.cert.pem' % (self.sslname, label))
                        cert_read = True
                        if sha256(str(cert).encode('utf-8')).hexdigest() != meta['cert']:
                            logger.warn("Appears that the file system has bad meta signatures (cert). Purging.")
                            for file_to_delete in glob.glob("usr/etc/certs/%s.%s.*" % (self.sslname, label)):
                                logger.warn("Removing bad file: %s" % file_to_delete)
                                os.remove(file_to_delete)
                            continue

                chain_read = False
                if getattr(self, "chain_%s" % label) is None:
                    if os.path.exists('usr/etc/certs/%s.%s.chain.pem' % (self.sslname, label)):
                        # print("setting chain!!!")
                        chain = yield read_file('usr/etc/certs/%s.%s.chain.pem' % (self.sslname, label))
                        chain_read = True
                        if sha256(str(chain).encode('utf-8')).hexdigest() != meta['chain']:
                            logger.warn("Appears that the file system has bad meta signatures (chain). Purging.")
                            for file_to_delete in glob.glob("usr/etc/certs/%s.%s.*" % (self.sslname, label)):
                                logger.warn("Removing bad file: %s" % file_to_delete)
                                os.remove(file_to_delete)
                            continue

                key_read = False
                if getattr(self, "key_%s" % label) is None:
                    if os.path.exists('usr/etc/certs/%s.%s.key.pem' % (self.sslname, label)):
                        key = yield read_file('usr/etc/certs/%s.%s.key.pem' % (self.sslname, label))
                        key_read = True
                        if sha256(str(key).encode('utf-8')).hexdigest() != meta['key']:
                            logger.warn("Appears that the file system has bad meta signatures (key). Purging.")
                            for file_to_delete in glob.glob("usr/etc/certs/%s.%s.*" % (self.sslname, label)):
                                logger.warn("Removing bad file: %s" % file_to_delete)
                                os.remove(file_to_delete)
                            continue

                logger.debug("Reading meta file for cert: {label}", label=label)

                def return_int(input):
                    try:
                        return int(input)
                    except Exception as e:
                        logger.warn("ERROR: Cannot convert to int: {e}", e=e)
                        return input

                if csr_read:
                    setattr(self, "csr_%s" % label, csr)
                if cert_read:
                    setattr(self, "cert_%s" % label, cert)
                if chain_read:
                    setattr(self, "chain_%s" % label, chain)
                if key_read:
                    setattr(self, "key_%s" % label, key)
                setattr(self, "%s_expires" % label, return_int(meta['expires']))
                setattr(self, "%s_created" % label, return_int(meta['created']))
                setattr(self, "%s_signed" % label, return_int(meta['signed']))
                setattr(self, "%s_submitted" % label, return_int(meta['submitted']))

                self.check_is_valid(label)
            else:
                setattr(self, "%s_is_valid" % label, False)

    def sync_to_file(self):
        if self.sync_to_file_calllater is None:
            logger.debug("Will backup certs in a bit.")
            self.sync_to_file_calllater = reactor.callLater(180, self._sync_to_file)
        elif self.sync_to_file_calllater.active() is False:
            self.sync_to_file_calllater = reactor.callLater(180, self._sync_to_file)
        elif self.sync_to_file_calllater.active() is True:
            self.sync_to_file_calllater.reset(180)
        else:
            logger.warn("sync to file in an unknown state. Will just save now. {state}", state=self.sync_to_file_calllater)
            self.sync_to_file_calllater = None
            self._sync_to_file()

    def _sync_to_file(self):
        """
        Sync current data to the file system. This allows for quick recovery if the database goes bad.
        :return:
        """
        logger.info("Backing up SSL Certs to file system.")

        for label in ['previous', 'current', 'next']:

            meta = {
                'created': getattr(self, "%s_created" % label),
                'expires': getattr(self, "%s_expires" % label),
                'signed': getattr(self, "%s_signed" % label),
                'submitted': getattr(self, "%s_submitted" % label),
                'key_type': self.key_type,
                'key_size': self.key_size,
            }

            if getattr(self, "cert_%s" % label) is None:
                meta['cert'] = None
                file = 'usr/etc/certs/%s.%s.cert.pem' % (self.sslname, label)
                if os.path.exists(file):
                    os.remove(file)
            else:
                meta['cert'] = sha256(str(getattr(self, "cert_%s" % label)).encode('utf-8')).hexdigest()
                save_file('usr/etc/certs/%s.%s.cert.pem' % (self.sslname, label),  getattr(self, "cert_%s" % label))

            if getattr(self, "chain_%s" % label) is None:
                meta['chain'] = None
                file = 'usr/etc/certs/%s.%s.chain.pem' % (self.sslname, label)
                if os.path.exists(file):
                    os.remove(file)
            else:
                meta['chain'] = sha256(str(getattr(self, "chain_%s" % label)).encode('utf-8')).hexdigest()
                save_file('usr/etc/certs/%s.%s.chain.pem' % (self.sslname, label), getattr(self, "chain_%s" % label))

            if getattr(self, "key_%s" % label) is None:
                meta['key'] = None
                file = 'usr/etc/certs/%s.%s.key.pem' % (self.sslname, label)
                if os.path.exists(file):
                    os.remove(file)
            else:
                meta['key'] = sha256(str(getattr(self, "key_%s" % label)).encode('utf-8')).hexdigest()
                save_file('usr/etc/certs/%s.%s.key.pem' % (self.sslname, label), getattr(self, "key_%s" % label))

            if label == 'next':
                if getattr(self, "csr_%s" % label) is None:
                    meta['csr'] = None
                    file = 'usr/etc/certs/%s.%s.csr.pem' % (self.sslname, label)
                    if os.path.exists(file):
                        os.remove(file)
                else:
                    meta['csr'] = sha256(str(getattr(self, "csr_%s" % label)).encode('utf-8')).hexdigest()
                    save_file('usr/etc/certs/%s.%s.csr.pem' % (self.sslname, label), getattr(self, "csr_%s" % label))

            save_file('usr/etc/certs/%s.%s.meta' % (self.sslname, label), json.dumps(meta, separators=(',',':')))

    def check_updated_fqdn(self):
        if self._ParentLibrary.fqdn != self.cert_fqdn:
            logger.warn("FQDN changed for cert, will get new one: {sslname}", sslname=self.sslname)
            self.next_is_valid = None
            self.current_is_valid = None
            self.generate_new_csr(submit=True)

    def generate_new_csr(self, submit=False, force_new=False):
        """
        Requests a new csr to be generated. This uses the base class to do the heavy lifting.

        We usually don't submit the CSR at the time generation. This allows the CSR to be genearted ahead
        of when we actually need.

        :param submit: If true, will also submit the csr.
        :param force_new: Will create a new CSR regardless of the current state.
        :return:
        """
        # print("1 calling local generate_new_csr. Force: %s.  Is valid: %s" % (force_new, self.next_is_valid))
        if force_new is True:
            self.clean_section('next')
        else:
            # print("calling check is valid from generate new csr")
            self.check_is_valid('next')

        # print("2 calling local generate_new_csr. Force: %s.  Is valid: %s" % (force_new, self.next_is_valid))
        if self.next_is_valid is not None:
            if submit is True:
                if self.next_csr_generation_in_progress is True:
                    self.next_csr_submit_after_generation = True
                else:
                    self.submit_csr()
            else:
                logger.info("Was asked to generatre CSR, but we don't need it.")
            return

        logger.warn("generate_new_csr: {sslname}.  Submit: {submit}", sslname=self.sslname, submit=submit)
        # End local functions.
        request = {
            'sslname': self.sslname,
            'key_size': self.key_size,
            'key_type': self.key_type,
            'cn': self.cn,
            'sans': self.sans
        }
        # end local function defs

        if self.next_csr_generation_in_progress is True: # don't run twice!
            if submit is True:  # but if previously, we weren't going to submit it, we will now if requested.
                self.next_csr_submit_after_generation = True
            return

        self.next_csr_generation_in_progress = True
        self.next_csr_submit_after_generation = submit

        self.next_csr_generation_count = 0
        self.next_csr_generation_in_progress = True
        logger.debug("About to generate new csr request: {request}", request=request)

        try:
            self._ParentLibrary.generate_csr_queue.put(request, done_callback=self.generate_new_csr_done, done_arg={'submit':submit})
            return True
        except Exception as e:
            self.next_csr_generation_error_count += 1
            if self.next_csr_generation_error_count < 5:
                logger.warn("Error generating new CSR for '{sslname}'. Will retry in 15 seconds. Exception : {failure}",
                            sslname=self.sslname, failure=e)
                reactor.callLater(15, self.generate_new_csr)
            else:
                logger.error(
                    "Error generating new CSR for '{sslname}'. Too many retries, perhaps something wrong with our request. Exception : {failure}",
                    sslname=self.sslname, failure=e)
                self.next_csr_generation_in_progress = False
            return False

    def generate_new_csr_done(self, results, args):
        """
        Our CSR has been generated. Lets save it, and maybe subit it.

        :param results: The CSR and KEY.
        :param args: Any args from the queue.
        :param submit: True if we should submit it to yombo for signing.
        :return:
        """
        logger.warn("generate_new_csr_done: {sslname}", sslname=self.sslname)
        results = bytes_to_unicode(results)
        logger.info("generate_new_csr_done:results: results {results}", results=results)
        # logger.info("generate_new_csr_done:results: args {results}", results=args)
        self.key_next = results['key']
        self.csr_next = results['csr']
        # print("generate_new_csr_done csr: %s " % self.csr_next)
        save_file('usr/etc/certs/%s.next.csr.pem' % self.sslname, self.csr_next)
        save_file('usr/etc/certs/%s.next.key.pem' % self.sslname, self.key_next)
        self.next_created = int(time())
        self.sync_to_file()
        self.next_csr_generation_in_progress = False
        logger.debug("generate_new_csr_done:args: {args}", args=args)
        if args['submit'] is True:
            # print("calling submit_csr from generate_new_csr_done")
            self.submit_csr()

    def submit_csr(self):
        """
        Submit a CSR for signing, only if we have a CSR and KEY.
        :return:
        """
        # self.next_submitted = int(time())
        missing = []
        if self.csr_next is None:
            missing.append("CSR")
        if self.key_next is None:
            missing.append("KEY")

        # print("sslcert:submit_csr - csr_text: %s" % self.csr_next)
        if len(missing) == 0:
            request = self._ParentLibrary.send_csr_request(self.csr_next, self.sslname)
            logger.debug("Sending CSR Request from instance. Correlation id: {correlation_id}",
                         correlation_id=request['properties']['correlation_id'])
            self.next_submitted = int(time())
        else:
            logger.warn("Requested to submit CSR, but these are missing: {missing}", missing=".".join(missing))
            raise YomboWarning("Unable to submit CSR.")

    def yombo_csr_response(self, properties, body, correlation_info):
        """
        A response from a CSR request has been received. Lets process it.

        :param properties: Properties of the AQMP message.
        :param body: The message itself.
        :param correlation: Any correlation data regarding the AQMP message. We can check for timing, etc.
        :return:
        """
        logger.debug("Got CSR response: {body}", body=body)
        if body['status'] == "signed":
            self.chain_next = body['chain_text']
            self.cert_next = body['cert_text']
            self.cert_next = body['cert_text']
            self.next_signed = body['cert_signed']
            self.next_expires = body['cert_expires']
            self.next_is_valid = True
            self.sync_to_file()
            self.check_if_rotate_needed()
        # print("status: %s" % self.__dict__)

    def get_key(self):
        self.requested_locally = True
        return self.key

    # @inlineCallbacks
    # def delete(self):
    #     yield self._ParentLibrary._LocalDB.delete_sslcerts()
    #
    #     cert_path = self._Atoms.get('yombo.path') + "/usr/etc/certs/"
    #     cert_archive_path = self._Atoms.get('yombo.path') + "/usr/etc/certs/"
    #     pattern = "*_" + self.sslname + ".pem"
    #     for root, dirs, files in os.walk(cert_archive_path):
    #         for file in filter(lambda x: re.match(pattern, x), files):
    #             logger.debug("Removing file: {path}/{file}", path=cert_archive_path, file=file)
    #             # os.remove(os.path.join(root, file))
    #
    #     print("removing current cert file: %s" % self.filepath)
    #     # os.remove(self.filepath)
    #     if self.active_request is not None:
    #         #TODO: tell yombo we don't need this cert anymore.
    #         self.active_request = None
    #         del self._ParentLibrary.active_requests[self.sslname]

    def get(self):
        """
        Returns a signed cert, the key, and the chain.
        """
        if self.current_is_valid is True:
            logger.debug("Sending public signed cert details for {sslname}", sslname=self.sslname)
            return {
                'key': self.key_current,
                'cert': self.cert_current,
                'chain': self.chain_current,
                'expires': self.current_expires,
                'created': self.current_created,
                'signed': self.current_signed,
                'self_signed': False,
                'cert_file': self._ParentLibrary._Atoms.get('yombo.path') + '/usr/etc/certs/%s.current.cert.pem' % self.sslname,
                'key_file': self._ParentLibrary._Atoms.get('yombo.path') + '/usr/etc/certs/%s.current.key.pem' % self.sslname,
                'chain_file': self._ParentLibrary._Atoms.get('yombo.path') + '/usr/etc/certs/%s.current.chain.pem' %
                self.sslname,
            }
        else:
            logger.debug("Sending SELF SIGNED cert details for {sslname}", sslname=self.sslname)
            if self._ParentLibrary.self_signed_created is None:
                raise YomboWarning("Self signed cert not avail. Try restarting gateway.")
            else:
                return {
                    'key': self._ParentLibrary.self_signed_key,
                    'cert': self._ParentLibrary.self_signed_cert,
                    'chain': None,
                    'expires': self._ParentLibrary.self_signed_expires,
                    'created': self._ParentLibrary.self_signed_created,
                    'signed': self._ParentLibrary.self_signed_created,
                    'self_signed': True,
                    'cert_file': self._ParentLibrary._Atoms.get('yombo.path') + '/usr/etc/certs/sslcert_selfsigned.cert.pem',
                    'key_file': self._ParentLibrary._Atoms.get('yombo.path') + '/usr/etc/certs/%sslcert_selfsigned.key.pem',
                    'chain_file': None,
                }

    def _dump(self):
        """
        Returns a dictionary of the current attributes. This should only be used internally.

        :return:
        """
        return {
            'sslname': self.sslname,
            'cn': self.cn,
            'sans': self.sans,
            'update_callback_type': self.update_callback_type,
            'update_callback_component': self.update_callback_component,
            'update_callback_function': self.update_callback_function,
            'key_size': int(self.key_size),
            'key_type': self.key_type,
            'cert_previous': self.cert_previous,
            'chain_previous': self.chain_previous,
            'key_previous': self.key_previous,
            'previous_expires': None if self.previous_expires is None else int(self.previous_expires),
            'previous_created': None if self.previous_created is None else int(self.previous_created),
            'previous_signed': self.previous_signed,
            'previous_submitted': self.previous_submitted,
            'previous_is_valid': self.previous_is_valid,
            'cert_current': self.cert_current,
            'chain_current': self.chain_current,
            'key_current': self.key_current,
            'current_created': None if self.current_created is None else int(self.current_created),
            'current_expires': None if self.current_expires is None else int(self.current_expires),
            'current_signed': self.current_signed,
            'current_submitted': self.current_submitted,
            'current_is_valid': self.current_is_valid,
            'csr_next': self.csr_next,
            'cert_next': self.cert_next,
            'chain_next': self.chain_next,
            'key_next': self.key_next,
            'next_created': None if self.next_created is None else int(self.next_created),
            'next_expires': None if self.next_expires is None else int(self.next_expires),
            'next_signed': self.next_signed,
            'next_submitted': self.next_submitted,
            'next_is_valid': self.next_is_valid,
        }

    def __str__(self):
        """
        Print the sslname for the sslcert when printing this cert instance.
        """
        return self.sslname

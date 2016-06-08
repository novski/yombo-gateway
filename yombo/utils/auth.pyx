# cython: embedsignature=True
#This file was created by Yombo for use with Yombo Python Gateway automation
#software.  Details can be found at https://yombo.net
"""
Handles authentication items between gateway and any remote connection.  Has functions
to check nonce strength/validity. Also generates and checks auth tokens.

.. moduleauthor:: Mitch Schwenk <mitch-gw@yombo.net>

:copyright: Copyright 2012-2015 by Yombo.
:license: LICENSE for details.
"""
# Import python libraries
from hashlib import sha256
from operator import concat

def validateNonce(nonce, **kwargs):
    """
    Validate a nonce is at least minLength in size and have a certain
    amount of randomness. Using the default settings will match up
    with :py:func:`~yombo.core.helpers.generateRandom`.
    
    :param nonce: The nonce to validate.
    :type nonce: string
    :param kwarg minLength: Validate nonce meets minimum length, default 32.
    :type kwarg minLength: int
    :param kwarg randomness: Percentage of unique characters that comprise the nonce. Can't exceed 0.95, default 0.85.
    :type kwarg randomness: float
    :returns: int - If given nonce meets minimum requirements, true, otherwise it's false.

    **Usage**:

    .. code-block:: python


       from yombo.core.auth import validateNonce
       if validateNonce(incomingNonce, minLength=32, randomness=0.70):
           logger.debug("The nonce is valid.")
       else:
           logger.debug("The nonce doesn't meet the minimum security requirements.")
    """
    import collections

    minLength =  kwargs.get('minLength', 32)
    randomness =  kwargs.get('randomness', 0.60)

    if len(nonce) < minLength:
        return False

    d = collections.defaultdict(int)

    if randomness > 0.70:
        randomness = 0.70
    elif randomness < 0.10:
        randomness = 0.10

    randomChars = int(minLength * randomness)
    if randomChars > 15:
        randomChars = 15
    for c in nonce:  #now check to make sure the nonce is random enough.
        d[c] += 1
    if len(d) < randomChars:
        return False

    return True

def checkToken(authToken, *components):
    """
    Check if authToken is valid for the given components.
    
    This method is used to validate a hash generated by :py:func:`generateToken`
    and matches the given input components.
    
    **Usage**:

    .. code-block:: python

       from yombo.core.auth import checkToken
       if checkToken(GivenToken, myPasswordHash, serverNonce, clientNonce):
           logger.debug("The authentication token is valid.")
       else:
           logger.debug("The authentication token is ** NOT ** valid..")

    :param authToken: The given hash to validate.
    :type authToken: string
    :param components: Any number of arguments to form a hash from.
    :type components: kwargs
    :returns: Bool - If given authToken matches up with new generated token, returns true, otherwise it's false.
    """
    return (sha256(reduce(concat, components)).hexdigest() == authToken)

def generateToken(*components):
    """
    Accepts any number of arguments, concatenates them together as a single
    string, and generates an sha256 hash.
    
    Yombo uses hashes to validate credentials and other items. This allows
    the gateway, servers, controllers, etc, to send hashes of hashes without
    exposing the true hash.  Combined with nonce's, this protects
    the real hash of users, gateways, etc, from behing revealed.

    :py:func:`checkToken` is used to check if a given hash is valid with the same input arguments.

    **Usage**:

    .. code-block:: python

        from yombo.core.auth import generateToken
        newHash = generateToken(myPasswordHash, serverNonce, clientNonce)
        logger.debug("The hash is: %s" % newHash)
    
    :param components: Any number of arguments to form a hash from.
    :type components: kwargs
    :return: An sha256 hash of the given components.
    :rtype: string
    
    """
    return sha256(reduce(concat, components)).hexdigest()
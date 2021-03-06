#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# TODO make sure the HTTPS certificate is verified

import suds
import suds.client
import suds.resolver
from suds.plugin import MessagePlugin
import logging
import sys

handler = logging.StreamHandler(sys.stderr)
logger = logging.getLogger('suds.transport.http')
logger.setLevel(logging.DEBUG), handler.setLevel(logging.DEBUG)
logger.addHandler(handler)

class OutGoingFilter(logging.Filter):
    def filter(self, record):
        return record.msg.startswith('sending:')

handler.addFilter(OutGoingFilter())


class AttrSetterPlugin(MessagePlugin):

    def __init__(self, attr_name, attr_val, target_name, target_path='Body'):
        self.target_path = target_path
        self.target_name = target_name
        self.attr_name = attr_name
        self.attr_val = attr_val

    def marshalled(self, context):
        def find_targets(target_path, target_name):
            separator = '/'
            current_path = target_path
            for element in context.envelope.childAtPath(target_path).children:
                if str(element.name) == target_name:
                    targets.append(element)
                find_targets(target_path + separator + element.name, target_name)

        targets = []
        if self.target_name:
            find_targets(self.target_path, self.target_name)
        else:
            targets = [context.envelope.childAtPath(self.target_path)]

        for target in targets:
            target.set(self.attr_name, self.attr_val)


class PosGateway():
    '''a class to talk SOAP to the HPS Exchange POS Gateway'''

    live_url = 'https://posgateway.secureexchange.net/Hps.Exchange.PosGateway/PosGatewayService.asmx?wsdl'
    test_url = 'https://posgateway.cert.secureexchange.net/Hps.Exchange.PosGateway/PosGatewayService.asmx?wsdl'

    def __init__(self, licenseid, siteid, deviceid,
                 username, password, tokenvalue=None,
                 sitetrace=None, developerid=None, versionnbr=None,
                 clerkid=None,
                 url=test_url):

        if len(username) > 20:
            raise Exception('UserName must be no longer than 20 characters')

        trackDataPlugin = AttrSetterPlugin(attr_name='method',
                                           attr_val='swipe',
                                           target_path='Body/PosRequest/Ver1.0/Transaction',
                                           target_name='TrackData')

        self.client = suds.client.Client(url, plugins=[trackDataPlugin])

        # required
        self.licenseid = licenseid
        self.siteid = siteid
        self.deviceid = deviceid
        self.username = username
        self.password = password
        # optional
        self.tokenvalue = tokenvalue
        self.sitetrace = sitetrace
        self.developerid = developerid
        self.versionnbr = versionnbr
        self.clerkid = clerkid
        self.url = url


    def _newrequest(self, transaction, value='PlaceholderText'):
        '''create a new PosRequest and populate the headers'''
        request = self.client.factory.create('ns0:PosRequest')
        request['Ver1.0']['Transaction'][transaction] = value
        # required
        request['Ver1.0']['Header']['LicenseId'] = self.licenseid
        request['Ver1.0']['Header']['SiteId'] = self.siteid
        request['Ver1.0']['Header']['DeviceId'] = self.deviceid
        request['Ver1.0']['Header']['UserName'] = self.username
        request['Ver1.0']['Header']['Password'] = self.password
        # optional
        if self.tokenvalue:
            request['Ver1.0']['Header']['TokenValue'] = self.tokenvalue
        if self.sitetrace:
            request['Ver1.0']['Header']['SiteTrace'] = self.sitetrace
        if self.developerid:
            request['Ver1.0']['Header']['DeveloperID'] = self.developerid
        if self.versionnbr:
            request['Ver1.0']['Header']['VersionNbr'] = self.versionnbr
        if self.clerkid:
            request['Ver1.0']['Header']['ClerkID'] = self.clerkid
        return request


    def _newcreditrequest(self, transaction, e3data, amount):
        '''create a new PosRequest for a credit transaction'''

        block1 = dict()
        block1['Block1'] = dict()
        block1['Block1']['Amt'] = amount
        block1['Block1']['CardData'] = dict()
        block1['Block1']['CardData']['TrackData'] = e3data
        block1['Block1']['CardData']['EncryptionData'] = dict()
        block1['Block1']['CardData']['EncryptionData']['Version'] = '01'

        posrequest = self._newrequest(transaction)
        posrequest['Ver1.0']['Transaction'][transaction] = block1
        return posrequest


    def _checkresponse(self, posresponse):
        """ returns tuple (bool success, response) """
        responsemsg = posresponse['Ver1.0']['Header']['GatewayRspMsg']
        success = responsemsg == 'Success'
        return success, dict(posresponse)


    def _dotransaction(self, posrequest):
        """
        run a transaction, some don't have a value but suds needs
        something there to generate the XML properly
        """
        posresponse = self.client.service.DoTransaction(posrequest['Ver1.0'])
        return self._checkresponse(posresponse)


    def testcredentials(self):
        '''test the credentials setup in the object'''
        return self._dotransaction(self._newrequest('TestCredentials'))


    def creditaccountverify(self, e3data):
        """ verify a credit account without making a transaction """
        posrequest = self._newcreditrequest('CreditAccountVerify', e3data, '0.00')
        posrequest["Ver1.0"]["Transaction"]["CreditAccountVerify"]["Block1"].pop("Amt")
        return self._dotransaction(posrequest)


    def creditsale(self, e3data, amount):
        '''make a CreditSale transaction of a given amount'''
        posrequest = self._newcreditrequest('CreditSale', e3data, amount)
        return self._dotransaction(posrequest)


    def creditreversal(self, e3data, amount):
        '''make a CreditReversal transaction of a given amount'''
        posrequest = self._newcreditrequest('CreditReversal', e3data, amount)
        return self._dotransaction(posrequest)


    def batchclose(self):
        '''close a batch of transactions on the POS Gateway'''
        return self._dotransaction(self._newrequest('BatchClose'))


if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    #logging.getLogger('suds.client').setLevel(logging.DEBUG)
    #logging.getLogger('suds.transport').setLevel(logging.DEBUG)
    #logging.getLogger('suds.xsd.schema').setLevel(logging.DEBUG)
    #logging.getLogger('suds.wsdl').setLevel(logging.DEBUG)

    pos = PosGateway('12345', '12345', '12345678', '12345678A', '$password',
                        developerid='012345', versionnbr='1234')
    #pos.testcredentials()
    e3data = open('testdata.txt', 'r').readline().rstrip('\n')
    print pos.creditsale(e3data, 5.23)
    print pos.creditreversal(e3data, 5.00)
    

from flask import Flask, Response

app = Flask(__name__)

@app.route('/simple-xml')
def simple_xml():
    xml_data = '''
    <Response>
        <ReturnValue>
            <Items>
                <Item>
                    <Text>One</Text>
                    <Value>1</Value>
                </Item>
                <Item>
                    <Text>Two</Text>
                    <Value>2</Value>
                </Item>
                <Item>
                    <Text>Three</Text>
                    <Value>3</Value>
                </Item>
            </Items>
        </ReturnValue>
    </Response>
    '''
    return Response(xml_data.encode('utf-16'), mimetype='application/xml')

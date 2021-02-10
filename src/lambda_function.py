import json
import boto3
import logging
import csv
import os
from datetime import date, datetime

# Configure logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

#Instansiate clients
my_ce = boto3.client('ce')
my_org = boto3.client('organizations')
my_s3 = boto3.resource('s3')

#Get S3 Bucketname
bucket_name=os.getenv('output_bucket')

#Determine current month and year
def get_dates():

    today = date.today()
    #today = date(2020,1,13)
    
    if today.month == 1:
        one_month_ago = today.replace(year=today.year - 1, month=12)
    else:
        extra_days = 0
        while True:
            try:
                one_month_ago = today.replace(month=today.month - 1, day=today.day - extra_days)
                break
            except ValueError:
                extra_days += 1
    
    start_date = one_month_ago.strftime('%Y-%m' + '-01')
    end_date = today.strftime('%Y-%m' + '-01')
    
    return[start_date, end_date]

#Gather account details
def get_accounts(dates):

    index = 0
    indextags = 0
    result_dict = {}
    output_filename = 'costinformation-' + dates[0] +'.csv'
    
    #Get all AWS Accounts from AWS Organizations
    my_accounts = my_org.list_accounts() 

    #Instanciate the output file
    with open('/tmp/results.csv', 'w+', newline='') as csvfile:
        fieldnames = ['AccountID', 'Email', 'Name', 'Status', 'Cost', 'StartDate', 'EndDate', 'Project', 'Cost Center', 'Owner']
        writer = csv.DictWriter(csvfile, delimiter=',', fieldnames=fieldnames)
        writer.writeheader()

        while index < len(my_accounts['Accounts']):

            #Write basic headers to the CSV file
            result_dict[str(index)] = {}
            result_dict[str(index)]['AccountID'] = my_accounts['Accounts'][index]['Id']
            result_dict[str(index)]['Email'] = my_accounts['Accounts'][index]['Email']
            result_dict[str(index)]['Name'] = my_accounts['Accounts'][index]['Name']
            result_dict[str(index)]['Status'] = my_accounts['Accounts'][index]['Status']

            #Call for tags on each AWS Account in AWS Organizations          
            id_tags = my_org.list_tags_for_resource(
                    ResourceId=my_accounts['Accounts'][index]['Id']
            )
            result_dict[str(index)]['Tags'] = {}
            while indextags < len(id_tags['Tags']):
                result_dict[str(index)]['Tags'][str(indextags)] = {}
                result_dict[str(index)]['Tags'][str(indextags)]['Key'] = id_tags['Tags'][indextags]['Key']
                result_dict[str(index)]['Tags'][str(indextags)]['Value'] = id_tags['Tags'][indextags]['Value']

                if id_tags['Tags'][indextags]['Key'] == 'Cost Center':
                    cost_center_value = id_tags['Tags'][indextags]['Value']
                if id_tags['Tags'][indextags]['Key'] == 'Owner':
                    owner_value = id_tags['Tags'][indextags]['Value']
                if id_tags['Tags'][indextags]['Key'] == 'Project':
                    project_value = id_tags['Tags'][indextags]['Value']

                indextags = indextags + 1
            
            #Call for cost on each AWS Account
            account_cost = my_ce.get_cost_and_usage(
                TimePeriod={
                    'Start': str(dates[0]),
                    'End': str(dates[1])
                },
                Granularity='MONTHLY',
                Filter = {
                    "And": [{
                        "Dimensions": {
                            "Key": "LINKED_ACCOUNT",
                            "Values": [my_accounts['Accounts'][index]['Id']]
                        }
                    },
                    {
                        "Not": {
                            "Dimensions": {
                                "Key": "RECORD_TYPE",
                                "Values": ["Credit", "Refund"]
                            }
                        }
                    }]
                },
                Metrics=[
                    'BlendedCost',
                ]
            )        
            result_dict[str(index)]['Cost'] = {}
            result_dict[str(index)]['Cost'] = account_cost['ResultsByTime'][0]['Total']['BlendedCost']

            #Write line to the CSV file
            writer.writerow({'AccountID': my_accounts['Accounts'][index]['Id'], 'Email': my_accounts['Accounts'][index]['Email'], 'Name': my_accounts['Accounts'][index]['Name'], 'Status': my_accounts['Accounts'][index]['Status'], 'Cost': account_cost['ResultsByTime'][0]['Total']['BlendedCost']['Amount'], 'StartDate': dates[0], 'EndDate': dates[1], 'Project': project_value, 'Cost Center': cost_center_value, 'Owner': owner_value})

            indextags = 0
            index = index + 1

    #Write CSV file to S3        
    my_s3.Object(bucket_name, output_filename).upload_file('/tmp/results.csv')  
        
    return [result_dict, output_filename]

#Main function
def lambda_handler(event, context):
    
    #Get the start- and end date within the current month    
    dates = get_dates()
    
    #Pass date information and do the account details processing
    account_data = get_accounts(dates)
    logger.info('Accounts Information:' + json.dumps(account_data[0], indent=2))
    logger.info('Output Filename:' + json.dumps(account_data[1], indent=2))

    return {
        'statusCode': 200,
        'body': json.dumps('Billing file has been written to: ' + account_data[1])
    }
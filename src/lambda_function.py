import json
import boto3
import logging
import csv
import os
from datetime import date
from dateutil.relativedelta import relativedelta
# Configure logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)
#Instansiate clients
my_ce = boto3.client('ce')
my_org = boto3.client('organizations')
my_s3 = boto3.resource('s3')
#Get S3 Bucketname
bucket_name=os.getenv('output_bucket')
#Get Cost Reporting Tags
cost_reporting_tags = {'Cost Center','Project','Owner'}
#Determine current month and year
def get_dates():
    start_date = (date.today() + relativedelta(months=-1)).replace(day=1).strftime('%Y-%m-%d')
    end_date = date.today().replace(day=1).strftime('%Y-%m-%d')
    return[start_date, end_date]
#Gather account details
def get_accounts(dates):
    result_dict = {}
    output_filename = 'costinformation-{}.csv'.format(dates[0])
    result_dict = {}
    #Instanciate the output file
    with open('/tmp/results.csv', 'w+', newline='') as csvfile:
        fieldnames = ['AccountID', 'Email', 'Name', 'Status', 'Cost', 'StartDate', 'EndDate']
        fieldnames += cost_reporting_tags
        writer = csv.DictWriter(csvfile, delimiter=',', fieldnames=fieldnames)
        writer.writeheader()
        #Get all AWS Accounts from AWS Organizations
        accounts_paginator = my_org.get_paginator('list_accounts')
        accounts_pages = accounts_paginator.paginate()
        for account_page in accounts_pages:
            for account in account_page['Accounts']:
                account_dict = {}
                #Write basic headers to the CSV file
                account_dict['AccountID'] = account['Id']
                account_dict['Email'] = account['Email']
                account_dict['Name'] = account['Name']
                account_dict['Status'] = account['Status']
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
                                "Values": [account['Id']]
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
                account_dict['Cost'] = account_cost['ResultsByTime'][0]['Total']['BlendedCost']['Amount']
                account_dict['StartDate'] = dates[0]
                account_dict['EndDate'] = dates[1]    
                tags = {}
                for crt in cost_reporting_tags:
                    tags[crt] = ''
                #Call for tags on each AWS Account in AWS Organizations          
                id_tags = my_org.list_tags_for_resource(ResourceId=account['Id'])
                for tag in id_tags['Tags']:
                    if tag['Key'] in cost_reporting_tags:
                        tags[tag['Key']] = tag['Value']
                account_dict.update(tags)
                result_dict[account['Id']] = account_dict
                #Write line to the CSV file
                writer.writerow(account_dict)
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
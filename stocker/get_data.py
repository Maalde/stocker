import pandas as pd
from pandas_datareader import data
import requests
import datetime as dt
from pytrends.request import TrendReq


def main(stock, years=1):
    end = dt.datetime.today().strftime('%Y-%m-%d')
    start = (dt.datetime.today() - dt.timedelta(days=365*years)).strftime('%Y-%m-%d')
    df = data.DataReader(stock, 'yahoo', start, end)

    return df, start, end


def company_name(stock):
    url = "http://d.yimg.com/autoc.finance.yahoo.com/autoc?query={}&region=1&lang=en".format(stock)
    company = requests.get(url).json()['ResultSet']['Result'][0]['name']

    return company


# Data from Google Trends
def get_interest(company, timeframe):
    pytrend = TrendReq()
    pytrend.build_payload(kw_list=[company], timeframe=timeframe)
    result = pytrend.interest_over_time().drop('isPartial', axis=1)

    return result


def add_interest(df, company, years=1):
    delta = int((365 * years / 73) - 1)
    since = (dt.datetime.today() - dt.timedelta(days=365 * years)).strftime('%Y-%m-%d')
    until = (dt.datetime.today() - dt.timedelta(days=73 * delta)).strftime('%Y-%m-%d')
    timeframe = since + ' ' + until
    trends = get_interest(company, timeframe)
    for x in range(delta):
        since = (dt.datetime.today() - dt.timedelta(days=73 * (delta - x))).strftime('%Y-%m-%d')
        until = (dt.datetime.today() - dt.timedelta(days=73 * (delta - 1 - x))).strftime('%Y-%m-%d')
        timeframe = since + ' ' + until
        trends.append(get_interest(company, timeframe))

    trends.rename(columns={company: 'Interest'}, inplace=True)
    trends.index.names = ['Date']
    df = df.merge(trends, how='left', on='Date')  # Add Interest column from Google Trends API - pytrends
    df.Interest.interpolate(inplace=True)

    return df


def add_wiki_views(df, company, start, end):  # Data from Wikipedia
    start = start.replace('-', '')
    end = end.replace('-', '')
    link = 'https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/all-agents' \
           '/{s}/daily/{st}/{end}'.format(s=company, st=start, end=end)
    wiki_data = requests.get(link).json()
    views = [i['views'] for i in wiki_data['items']]
    date = [i['timestamp'] for i in wiki_data['items']]
    date = [dt.datetime.strptime(date[:-2], '%Y%m%d').date().strftime('%Y-%m-%d') for date in date]
    wiki_views = pd.DataFrame(views, index=date, columns=['Wiki_views'])
    wiki_views.index.name = 'Date'
    wiki_views.index = pd.to_datetime(wiki_views.index)

    df = df.merge(wiki_views, how='left', on='Date')  # Add Wiki_views column from Wikipedia API
    df.Wiki_views.ffill(inplace=True)

    return df


def add_rsi(df, period):    # Calculate RSI
    df['Change'] = df.Close - df.Open  # calculating gains and losses in a new column
    df['Gain'] = df.Change[df.Change > 0]  # new column of gains
    df['Loss'] = df.Change[df.Change < 0] * (-1)  # new column of losses
    df.drop(columns=['Change'], inplace=True)  # remove the column change

    # Filling missing values with 0
    df.Gain.fillna(0, inplace=True)
    df.Loss.fillna(0, inplace=True)

    df['Again'] = df.Gain.rolling(period).mean()  # calculate the average gain in the last 14 periods
    df['Aloss'] = df.Loss.rolling(period).mean()  # calculate the average loss in the last 14 periods

    df['RS'] = df.Again / df.Aloss  # calculating RS
    df['RSI'] = 100 - (100 / (1 + (df.Again / df.Aloss)))  # calculating RSI
    df.drop(columns=['Gain', 'Loss', 'Again', 'Aloss', 'RS'], inplace=True)  # remove undesired columns

    return df


def add_k(df, period):   # Calculate Stochastic Oscillator (%K)
    df['L14'] = df.Low.rolling(period).min()  # find the lowest price in the last 14 periods
    df['H14'] = df.High.rolling(period).max()  # find the highest price in the last 14 periods
    df['%K'] = ((df.Close - df.L14) / (df.H14 - df.L14)) * 100
    df.drop(columns=['L14', 'H14'], inplace=True)  # remove columns L14 and H14

    return df


def add_r(df, period):  # Calculate Larry William indicator (%R)
    df['HH'] = df.High.rolling(period).max()  # find the highest high price in the last 14 periods
    df['LL'] = df.Low.rolling(period).min()  # find the lowest low price in the last 14 periods
    df['%R'] = ((df.HH - df.Close) / (df.HH - df.LL)) * (-100)
    df.drop(columns=['HH', 'LL'], inplace=True)  # remove columns HH and LL

    return df


def total(stock, years=1, interest=False, wiki_views=False, indicators=False, period=14):
    df, start, end = main(stock, years=years)
    company = company_name(stock)

    if interest:
        df = add_interest(df, company, years=years)  # adding Interest from Google Trends.

    if wiki_views:
        df = add_wiki_views(df, company, start, end)

    if indicators:
        df = add_k(df, period)  # generating %K column.
        df = add_r(df, period)  # generating %R column.
        df = add_rsi(df, period)  # generating RSI column.

    df = df.dropna()

    return df


def correlation(stock, years=1, interest=False, wiki_views=False, indicators=False, period=14, complete=True, limit=0.5):
    df = total(stock, years, interest, wiki_views, indicators, period)

    if complete:
        features = df.corr().Close
    else:
        features = df.corr().Close[df.corr().Close > limit].index.tolist()

    return features

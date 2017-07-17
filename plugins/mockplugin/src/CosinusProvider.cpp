#include "CosinusProvider.h"

#include <Data/DataProviderParameters.h>
#include <Data/ScalarSeries.h>

#include <cmath>

#include <QDateTime>
#include <QThread>

Q_LOGGING_CATEGORY(LOG_CosinusProvider, "CosinusProvider")

std::shared_ptr<IDataSeries> CosinusProvider::retrieveData(const SqpDateTime &dateTime) const
{
    auto dataIndex = 0;

    // Gets the timerange from the parameters
    double freq = 100.0;
    double start = dateTime.m_TStart * freq; // 100 htz
    double end = dateTime.m_TEnd * freq;     // 100 htz

    // We assure that timerange is valid
    if (end < start) {
        std::swap(start, end);
    }

    // Generates scalar series containing cosinus values (one value per second)
    auto scalarSeries
        = std::make_shared<ScalarSeries>(end - start, Unit{QStringLiteral("t"), true}, Unit{});

    for (auto time = start; time < end; ++time, ++dataIndex) {
        const auto timeOnFreq = time / freq;
        scalarSeries->setData(dataIndex, timeOnFreq, std::cos(timeOnFreq));
    }
    return scalarSeries;
}

void CosinusProvider::requestDataLoading(QUuid token, const DataProviderParameters &parameters)
{
    qCDebug(LOG_CosinusProvider()) << "CosinusProvider::requestDataLoading"
                                   << QThread::currentThread()->objectName();
    // NOTE: Try to use multithread if possible
    const auto times = parameters.m_Times;
    for (const auto &dateTime : qAsConst(times)) {
        auto scalarSeries = this->retrieveData(dateTime);
        emit dataProvided(token, scalarSeries, dateTime);
    }
}

void CosinusProvider::requestDataAborting(QUuid identifier)
{
    // TODO
}

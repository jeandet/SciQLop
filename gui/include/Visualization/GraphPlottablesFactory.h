#ifndef SCIQLOP_GRAPHPLOTTABLESFACTORY_H
#define SCIQLOP_GRAPHPLOTTABLESFACTORY_H

#include <Data/SqpDateTime.h>

#include <QLoggingCategory>
#include <QVector>

#include <memory>

Q_DECLARE_LOGGING_CATEGORY(LOG_GraphPlottablesFactory)

class IDataSeries;
class QCPAbstractPlottable;
class QCustomPlot;
class Variable;

/**
 * @brief The GraphPlottablesFactory class aims to create the QCustomPlot components relative to a
 * variable, depending on the data series of this variable
 */
struct GraphPlottablesFactory {
    /**
     * Creates (if possible) the QCustomPlot components relative to the variable passed in
     * parameter, and adds these to the plot passed in parameter.
     * @param variable the variable for which to create the components
     * @param plot the plot in which to add the created components. It takes ownership of these
     * components.
     * @return the list of the components created
     */
    static QVector<QCPAbstractPlottable *> create(std::shared_ptr<Variable> variable,
                                                  QCustomPlot &plot) noexcept;

    static void updateData(QVector<QCPAbstractPlottable *> plotableVect, IDataSeries *dataSeries,
                           const SqpDateTime &dateTime);
};

#endif // SCIQLOP_GRAPHPLOTTABLESFACTORY_H
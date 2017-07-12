#ifndef SCIQLOP_VARIABLE_H
#define SCIQLOP_VARIABLE_H

#include <Data/SqpDateTime.h>

#include <QLoggingCategory>
#include <QObject>

#include <Common/MetaTypes.h>
#include <Common/spimpl.h>

Q_DECLARE_LOGGING_CATEGORY(LOG_Variable)

class IDataSeries;
class QString;

/**
 * @brief The Variable class represents a variable in SciQlop.
 */
class Variable : public QObject {

    Q_OBJECT

public:
    explicit Variable(const QString &name, const SqpDateTime &dateTime);

    QString name() const noexcept;
    SqpDateTime dateTime() const noexcept;
    void setDateTime(const SqpDateTime &dateTime) noexcept;

    /// @return the data of the variable, nullptr if there is no data
    IDataSeries *dataSeries() const noexcept;

    bool contains(const SqpDateTime &dateTime) const noexcept;
    bool intersect(const SqpDateTime &dateTime) const noexcept;
    bool isInside(const SqpDateTime &dateTime) const noexcept;

public slots:
    void setDataSeries(std::shared_ptr<IDataSeries> dataSeries) noexcept;

signals:
    void updated();

private:
    class VariablePrivate;
    spimpl::unique_impl_ptr<VariablePrivate> impl;
};

// Required for using shared_ptr in signals/slots
SCIQLOP_REGISTER_META_TYPE(VARIABLE_PTR_REGISTRY, std::shared_ptr<Variable>)

#endif // SCIQLOP_VARIABLE_H

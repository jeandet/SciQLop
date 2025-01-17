#include "FuzzingOperations.h"
#include "FuzzingUtils.h"

#include <Data/IDataProvider.h>

#include <Variable/Variable.h>
#include <Variable/VariableController2.h>

#include <QUuid>

#include <functional>

Q_LOGGING_CATEGORY(LOG_FuzzingOperations, "FuzzingOperations")

namespace {

struct CreateOperation : public IFuzzingOperation {
    bool canExecute(VariableId variableId, const FuzzingState &fuzzingState) const override
    {
        // A variable can be created only if it doesn't exist yet
        return fuzzingState.variableState(variableId).m_Variable == nullptr;
    }

    void execute(VariableId variableId, FuzzingState &fuzzingState,
                 VariableController2 &variableController,
                 const Properties &properties) const override
    {
        // Retrieves metadata pool from properties, and choose one of the metadata entries to
        // associate it with the variable
        auto metaDataPool = properties.value(METADATA_POOL_PROPERTY).value<MetadataPool>();
        auto variableMetadata = RandomGenerator::instance().randomChoice(metaDataPool);

        // Retrieves provider
        auto variableProvider
            = properties.value(PROVIDER_PROPERTY).value<std::shared_ptr<IDataProvider> >();

        auto variableName = QString{"Var_%1"}.arg(QUuid::createUuid().toString());
        qCInfo(LOG_FuzzingOperations()).noquote() << "Creating variable" << variableName
                                                  << "(metadata:" << variableMetadata << ")...";

        auto newVariable
            = variableController.createVariable(variableName, variableMetadata, variableProvider, properties.value(INITIAL_RANGE_PROPERTY).value<DateTimeRange>());

        // Updates variable's state
        auto &variableState = fuzzingState.variableState(variableId);
        variableState.m_Range = properties.value(INITIAL_RANGE_PROPERTY).value<DateTimeRange>();
        std::swap(variableState.m_Variable, newVariable);
    }
};

struct DeleteOperation : public IFuzzingOperation {
    bool canExecute(VariableId variableId, const FuzzingState &fuzzingState) const override
    {
        // A variable can be delete only if it exists
        return fuzzingState.variableState(variableId).m_Variable != nullptr;
    }

    void execute(VariableId variableId, FuzzingState &fuzzingState,
                 VariableController2 &variableController, const Properties &) const override
    {
        auto &variableState = fuzzingState.variableState(variableId);

        qCInfo(LOG_FuzzingOperations()).noquote() << "Deleting variable"
                                                  << variableState.m_Variable->name() << "...";
        variableController.deleteVariable(variableState.m_Variable);

        // Updates variable's state
        variableState.m_Range = INVALID_RANGE;
        variableState.m_Variable = nullptr;

        // Desynchronizes the variable if it was in a sync group
        auto syncGroupId = fuzzingState.syncGroupId(variableId);
        fuzzingState.desynchronizeVariable(variableId, syncGroupId);
    }
};

/**
 * Defines a move operation through a range.
 *
 * A move operation is determined by three functions:
 * - Two 'move' functions, used to indicate in which direction the beginning and the end of a range
 * are going during the operation. These functions will be:
 * -- {<- / <-} for pan left
 * -- {-> / ->} for pan right
 * -- {-> / <-} for zoom in
 * -- {<- / ->} for zoom out
 * - One 'max move' functions, used to compute the max delta at which the operation can move a
 * range, according to a max range. For exemple, for a range of {1, 5} and a max range of {0, 10},
 * max deltas will be:
 * -- {0, 4} for pan left
 * -- {6, 10} for pan right
 * -- {3, 3} for zoom in
 * -- {0, 6} for zoom out (same spacing left and right)
 */
struct MoveOperation : public IFuzzingOperation {
    using MoveFunction = std::function<double(double currentValue, double maxValue)>;
    using MaxMoveFunction = std::function<double(const DateTimeRange &range, const DateTimeRange &maxRange)>;

    explicit MoveOperation(MoveFunction rangeStartMoveFun, MoveFunction rangeEndMoveFun,
                           MaxMoveFunction maxMoveFun,
                           const QString &label = QStringLiteral("Move operation"))
            : m_RangeStartMoveFun{std::move(rangeStartMoveFun)},
              m_RangeEndMoveFun{std::move(rangeEndMoveFun)},
              m_MaxMoveFun{std::move(maxMoveFun)},
              m_Label{label}
    {
    }

    bool canExecute(VariableId variableId, const FuzzingState &fuzzingState) const override
    {
        return fuzzingState.variableState(variableId).m_Variable != nullptr;
    }

    void execute(VariableId variableId, FuzzingState &fuzzingState,
                 VariableController2 &variableController,
                 const Properties &properties) const override
    {
        auto &variableState = fuzzingState.variableState(variableId);
        auto variable = variableState.m_Variable;

        // Gets the max range defined
        auto maxRange = properties.value(MAX_RANGE_PROPERTY, QVariant::fromValue(INVALID_RANGE))
                            .value<DateTimeRange>();
        auto variableRange = variableState.m_Range;

        if (maxRange == INVALID_RANGE || variableRange.m_TStart < maxRange.m_TStart
            || variableRange.m_TEnd > maxRange.m_TEnd) {
            qCWarning(LOG_FuzzingOperations()) << "Can't execute operation: invalid max range";
            return;
        }

        // Computes the max delta at which the variable can move, up to the limits of the max range
        auto deltaMax = m_MaxMoveFun(variableRange, maxRange);

        // Generates random delta that will be used to move variable
        auto delta = RandomGenerator::instance().generateDouble(0, deltaMax);

        // Moves variable to its new range
        auto isSynchronized = !fuzzingState.syncGroupId(variableId).isNull();
        auto newVariableRange = DateTimeRange{m_RangeStartMoveFun(variableRange.m_TStart, delta),
                                         m_RangeEndMoveFun(variableRange.m_TEnd, delta)};
        qCInfo(LOG_FuzzingOperations()).noquote() << "Performing" << m_Label << "on"
                                                  << variable->name() << "(from" << variableRange
                                                  << "to" << newVariableRange << ")...";
        variableController.changeRange({variable}, newVariableRange);

        // Updates state
        fuzzingState.updateRanges(variableId, newVariableRange);
    }

    MoveFunction m_RangeStartMoveFun;
    MoveFunction m_RangeEndMoveFun;
    MaxMoveFunction m_MaxMoveFun;
    QString m_Label;
};

struct SynchronizeOperation : public IFuzzingOperation {
    bool canExecute(VariableId variableId, const FuzzingState &fuzzingState) const override
    {
        auto variable = fuzzingState.variableState(variableId).m_Variable;
        return variable != nullptr && !fuzzingState.m_SyncGroupsPool.empty()
               && fuzzingState.syncGroupId(variableId).isNull();
    }

    void execute(VariableId variableId, FuzzingState &fuzzingState,
                 VariableController2 &variableController, const Properties &) const override
    {
        auto &variableState = fuzzingState.variableState(variableId);

        // Chooses a random synchronization group and adds the variable into sync group
        auto syncGroupId = RandomGenerator::instance().randomChoice(fuzzingState.syncGroupsIds());
        qCInfo(LOG_FuzzingOperations()).noquote() << "Adding" << variableState.m_Variable->name()
                                                  << "into synchronization group" << syncGroupId
                                                  << "...";
        //variableController.onAddSynchronized(variableState.m_Variable, syncGroupId);

        // Updates state
        fuzzingState.synchronizeVariable(variableId, syncGroupId);

        variableController.changeRange({variableState.m_Variable}, variableState.m_Range);
    }
};

struct DesynchronizeOperation : public IFuzzingOperation {
    bool canExecute(VariableId variableId, const FuzzingState &fuzzingState) const override
    {
        auto variable = fuzzingState.variableState(variableId).m_Variable;
        return variable != nullptr && !fuzzingState.syncGroupId(variableId).isNull();
    }

    void execute(VariableId variableId, FuzzingState &fuzzingState,
                 VariableController2 &variableController, const Properties &) const override
    {
        auto &variableState = fuzzingState.variableState(variableId);

        // Gets the sync group of the variable
        auto syncGroupId = fuzzingState.syncGroupId(variableId);

        qCInfo(LOG_FuzzingOperations()).noquote() << "Removing" << variableState.m_Variable->name()
                                                  << "from synchronization group" << syncGroupId
                                                  << "...";
        //variableController.desynchronize(variableState.m_Variable, syncGroupId);

        // Updates state
        fuzzingState.desynchronizeVariable(variableId, syncGroupId);
    }
};

struct UnknownOperation : public IFuzzingOperation {
    bool canExecute(VariableId, const FuzzingState &) const override { return false; }

    void execute(VariableId, FuzzingState &, VariableController2 &,
                 const Properties &) const override
    {
    }
};

} // namespace

std::unique_ptr<IFuzzingOperation> FuzzingOperationFactory::create(FuzzingOperationType type)
{
    switch (type) {
        case FuzzingOperationType::CREATE:
            return std::make_unique<CreateOperation>();
        case FuzzingOperationType::DELETE:
            return std::make_unique<DeleteOperation>();
        case FuzzingOperationType::PAN_LEFT:
            return std::make_unique<MoveOperation>(
                std::minus<double>(), std::minus<double>(),
                [](const DateTimeRange &range, const DateTimeRange &maxRange) {
                    return range.m_TStart - maxRange.m_TStart;
                },
                QStringLiteral("Pan left operation"));
        case FuzzingOperationType::PAN_RIGHT:
            return std::make_unique<MoveOperation>(
                std::plus<double>(), std::plus<double>(),
                [](const DateTimeRange &range, const DateTimeRange &maxRange) {
                    return maxRange.m_TEnd - range.m_TEnd;
                },
                QStringLiteral("Pan right operation"));
        case FuzzingOperationType::ZOOM_IN:
            return std::make_unique<MoveOperation>(
                std::plus<double>(), std::minus<double>(),
                [](const DateTimeRange &range, const DateTimeRange &maxRange) {
                    Q_UNUSED(maxRange)
                    return range.m_TEnd - (range.m_TStart + range.m_TEnd) / 2.;
                },
                QStringLiteral("Zoom in operation"));
        case FuzzingOperationType::ZOOM_OUT:
            return std::make_unique<MoveOperation>(
                std::minus<double>(), std::plus<double>(),
                [](const DateTimeRange &range, const DateTimeRange &maxRange) {
                    return std::min(range.m_TStart - maxRange.m_TStart,
                                    maxRange.m_TEnd - range.m_TEnd);
                },
                QStringLiteral("Zoom out operation"));
        case FuzzingOperationType::SYNCHRONIZE:
            return std::make_unique<SynchronizeOperation>();
        case FuzzingOperationType::DESYNCHRONIZE:
            return std::make_unique<DesynchronizeOperation>();
        default:
            // Default case returns unknown operation
            break;
    }

    return std::make_unique<UnknownOperation>();
}

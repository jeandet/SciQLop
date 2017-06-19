#ifndef SCIQLOP_DATASERIES_H
#define SCIQLOP_DATASERIES_H

#include <Data/ArrayData.h>
#include <Data/IDataSeries.h>

#include <memory>

/**
 * @brief The DataSeries class is the base (abstract) implementation of IDataSeries.
 *
 * It proposes to set a dimension for the values ​​data
 *
 * @tparam Dim The dimension of the values data
 *
 */
template <int Dim>
class DataSeries : public IDataSeries {
public:
    /// @sa IDataSeries::xAxisData()
    std::shared_ptr<ArrayData<1> > xAxisData() override { return m_XAxisData; }

    /// @sa IDataSeries::xAxisUnit()
    Unit xAxisUnit() const override { return m_XAxisUnit; }

    /// @return the values dataset
    std::shared_ptr<ArrayData<Dim> > valuesData() const { return m_ValuesData; }

    /// @sa IDataSeries::valuesUnit()
    Unit valuesUnit() const override { return m_ValuesUnit; }

protected:
    /// Protected ctor (DataSeries is abstract)
    explicit DataSeries(std::shared_ptr<ArrayData<1> > xAxisData, Unit xAxisUnit,
                        std::shared_ptr<ArrayData<Dim> > valuesData, Unit valuesUnit)
            : m_XAxisData{xAxisData},
              m_XAxisUnit{std::move(xAxisUnit)},
              m_ValuesData{valuesData},
              m_ValuesUnit{std::move(valuesUnit)}
    {
    }

private:
    std::shared_ptr<ArrayData<1> > m_XAxisData;
    Unit m_XAxisUnit;
    std::shared_ptr<ArrayData<Dim> > m_ValuesData;
    Unit m_ValuesUnit;
};

#endif // SCIQLOP_DATASERIES_H
